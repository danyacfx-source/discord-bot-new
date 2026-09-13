import asyncio
import logging
import re
import time

from deep_translator import GoogleTranslator, MyMemoryTranslator

log = logging.getLogger("translate")

# Сохраняем структуру строки: заголовки, нумерацию, буллеты, цитаты.
_PREFIX_RE = re.compile(r"^(#{1,6}\s+|\d+\.\s+|[-*+]\s+|>\s?)")

# Inline-markdown Discord: код, зачёркивание, подчёркивание, жирный/курсив,
# спойлеры, ссылки. Такие участки вырезаются до перевода и вставляются обратно,
# чтобы движок их не испортил.
_INLINE_MD = re.compile(
    r"("
    r"`(?:[^`\n]|\\`)+`"
    r"|~~[^\n]+?~~"
    r"|__[^\n]+?__"
    r"|\*\*\*[^\n]+?\*\*\*"
    r"|\*\*[^\n]+?\*\*"
    r"|\*[^*\n][^\n]*?\*"
    r"|\|\|[^\n]+?\|\|"
    r"|\[[^\[\]\n]+?\]\([^()\n]+?\)"
    r")",
    re.DOTALL,
)

# Google не любит длинные тексты одним куском; MyMemory — максимум ~500 символов.
_GOOGLE_MAX = 4200
_MYMEMORY_MAX = 480

_ENGINE_TIMEOUT = 8
_LINE_TIMEOUT = 30
_GOOGLE_COOLDOWN = 60  # секунд: после неудачи Google пропускаем

# Асиевский API MyMemory требует региональные коды; источник всегда английский.
_MYMEMORY_LANGS = {
    "ru": "ru-RU",
    "uk": "uk-UA",
    "pl": "pl-PL",
    "de": "de-DE",
}

# Распознавание «ответа-ошибки» вместо перевода (лимиты, падения движков).
_ERROR_RE = re.compile(
    r"error\s*500|that'?s an error|there was an error|please try again later|"
    r"internal server error|invalid source language|mymemory warning|"
    r"you used all available free translations",
    re.IGNORECASE,
)


class _Translators:
    """Пара движков (Google + MyMemory) под конкретный целевой язык."""

    def __init__(self, target: str):
        self.google = GoogleTranslator(source="auto", target=target)
        self.mymemory = MyMemoryTranslator(
            source="en-GB", target=_MYMEMORY_LANGS.get(target, target)
        )


_ENGINES: dict[str, _Translators] = {}
_google_down: dict[str, float] = {}  # target_lang → monotonic timestamp, до которого Google пропускаем


def _get_engines(target: str) -> _Translators:
    if target not in _ENGINES:
        _ENGINES[target] = _Translators(target)
    return _ENGINES[target]


def _is_error(text: str) -> bool:
    if not text:
        return True
    return bool(_ERROR_RE.search(text))


def _split_by_length(text: str, limit: int) -> list[str]:
    """Режет текст по пробелам на куски <= limit без разрыва слов."""
    text = text.strip()
    if not text:
        return []
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip()
        if not text:
            break
    if text:
        parts.append(text)
    return parts


async def _call(engine, text: str, timeout: float) -> str | None:
    """Вызов синхронного движка без блокировки event loop и с таймаутом."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(engine.translate, text), timeout)
    except asyncio.TimeoutError:
        log.warning("Таймаут перевода (%s)", engine.__class__.__name__)
    except Exception as e:
        log.debug("%s не ответил: %s", engine.__class__.__name__, e)
    return None


async def _translate_text(engines: _Translators, text: str) -> str | None:
    """Перевод куска: Google целиком/по частям, при сбое — MyMemory. Возвращает None."""
    now = time.monotonic()
    google_cooldown = _google_down.get(engines.google.target, 0)
    use_google = now >= google_cooldown

    if use_google:
        parts = _split_by_length(text, _GOOGLE_MAX)
        google_done: list[str] = []
        for part in parts:
            out = await _call(engines.google, part, _ENGINE_TIMEOUT)
            if out and not _is_error(out):
                google_done.append(out.strip())
            else:
                google_done.append(None)
        if all(google_done):
            return " ".join(google_done)
        # Google упал — запоминаем и добиваем MyMemory.
        _google_down[engines.google.target] = now + _GOOGLE_COOLDOWN
        log.warning("Google недоступен, переключаюсь на MyMemory на %ds", _GOOGLE_COOLDOWN)
        mymem_done: list[str] = []
        for part in _split_by_length(text, _MYMEMORY_MAX):
            out = await _call(engines.mymemory, part, _ENGINE_TIMEOUT)
            mymem_done.append(out.strip() if out and not _is_error(out) else part)
        return " ".join(mymem_done)

    # Google на кулдауне — сразу MyMemory без ожидания.
    mymem_done: list[str] = []
    for part in _split_by_length(text, _MYMEMORY_MAX):
        out = await _call(engines.mymemory, part, _ENGINE_TIMEOUT)
        mymem_done.append(out.strip() if out and not _is_error(out) else part)
    return " ".join(mymem_done)


# Парные markdown-маркеры: открывающий и закрывающий совпадают.
_MD_PAIR_RE = re.compile(
    r"^(?P<open>\*\*\*|\*\*|__|~~|\*|\|\|)(?P<inner>.*?)(?P=open)$",
    re.DOTALL,
)
_MD_LINK_RE = re.compile(r"^\[(?P<label>[^\]]*)\]\((?P<url>[^()]*)\)$", re.DOTALL)


async def _translate_token(engines: _Translators, token: str) -> str:
    """Перевод содержимого markdown-токена: маркеры сохраняются в целости."""
    # Код обратными кавычками не переводим вообще.
    if token.startswith("`"):
        return token

    # Ссылка: переводим текст-подпись, URL оставляем как есть.
    m = _MD_LINK_RE.match(token)
    if m:
        label = m.group("label")
        if label.strip():
            translated = await _translate_text(engines, label)
            if translated:
                label = translated
        return f"[{label}]({m.group('url')})"

    # Парные маркеры: **жирный**, *курсив*, __подчёркнутый__, ~~зачёркнутый~~, ||спойлер||.
    m = _MD_PAIR_RE.match(token)
    if m:
        inner = m.group("inner")
        if inner.strip():
            translated = await _translate_text(engines, inner)
            if translated:
                inner = translated
        return m.group("open") + inner + m.group("open")

    return token


async def _translate_line(engines: _Translators, line: str) -> str:
    m = _PREFIX_RE.match(line)
    prefix = m.group(0) if m else ""
    rest = line[m.end():] if m else line

    if not rest.strip():
        return line

    # Разбиваем на текст и markdown-токены: чётные части — текст, нечётные — токены.
    pieces = _INLINE_MD.split(rest)
    out: list[str] = []
    for i, piece in enumerate(pieces):
        if i % 2 == 1:
            out.append(await _translate_token(engines, piece))
        elif piece.strip():
            try:
                res = await asyncio.wait_for(_translate_text(engines, piece), _LINE_TIMEOUT)
            except asyncio.TimeoutError:
                log.warning("Таймаут перевода строки, оставляю оригинал")
                res = None
            out.append(res if res is not None else piece)
        else:
            out.append(piece)
    return prefix + "".join(out)


async def async_translate_text(text: str, target_lang: str = "ru") -> str | None:
    """Перевод сообщения с сохранением markdown-разметки и пунктуации.

    Каждая строка переводится отдельно: префиксы (#, ##, -, 1., >) и
    разметка (**жирный**, *курсив*, ссылки, код, спойлеры) остаются
    нетронутыми, переводится только содержимое строки.
    """
    if not text or not text.strip():
        return None

    engines = _get_engines(target_lang)
    lines = text.splitlines()
    out_lines: list[str] = []
    for line in lines:
        out_lines.append(await _translate_line(engines, line))
    return "\n".join(out_lines)