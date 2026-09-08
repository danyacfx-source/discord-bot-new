import asyncio
import logging

from deep_translator import GoogleTranslator

log = logging.getLogger("translate")


async def async_translate_text(text: str, target_lang: str = "ru") -> str | None:
    if not text or not text.strip():
        return None
    try:
        def _sync():
            return GoogleTranslator(source="auto", target=target_lang).translate(text.strip())

        return await asyncio.to_thread(_sync)
    except Exception as e:
        log.warning("Ошибка перевода: %s", e)
        return None