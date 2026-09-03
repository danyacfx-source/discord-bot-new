import asyncio
from deep_translator import GoogleTranslator


async def async_translate_text(text: str, target_lang: str = "ru") -> str | None:
    try:
        def _sync():
            return GoogleTranslator(source="auto", target=target_lang).translate(text)
        return await asyncio.to_thread(_sync)
    except Exception as e:
        print(f"[TRANSLATE ERROR]: {e}")
        return None
