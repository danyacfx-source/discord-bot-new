import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands

import config
from translator import async_translate_text


# Контекст-меню регистрируется на уровне модуля: discord.py 2.7+ не даёт
# определять context_menu внутри класса кога.
@app_commands.context_menu(name="Перевести")
async def translate_context(interaction: discord.Interaction, message: discord.Message):
    text = _message_text(message)
    if not text:
        await interaction.response.send_message("❌ Сообщение без текста.", ephemeral=True)
        return

    await interaction.response.defer()
    translated = await async_translate_text(text, config.TRANSLATE_TARGET)
    if not translated:
        await interaction.followup.send("❌ Не удалось перевести.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🌐 Перевод • {message.author.display_name}",
        description=translated,
        color=config.EMBED_COLOR,
    )
    files = _image_files(message)
    if files:
        await interaction.followup.send(embed=embed, files=files)
    else:
        await interaction.followup.send(embed=embed)


def _message_text(message: discord.Message) -> str:
    """Текст: из content; если контента нет — из первого embed (Steam-фиды и т.п.)."""
    text = message.content.strip()
    if len(text) >= 2:
        return text
    for emb in message.embeds:
        part = "\n".join(x for x in [emb.title or "", emb.description or ""] if x)
        for f in emb.fields:
            part += f"\n**{f.name}**: {f.value}"
        if part.strip():
            return part.strip()
    return ""


def _image_files(message: discord.Message) -> list[discord.Attachment]:
    """Картинки из сообщения (прикреплённые), которые поедят вместе с переводом."""
    return [
        a for a in message.attachments
        if a.content_type and a.content_type.startswith("image/")
    ]


class TranslateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Тонкий кулдаун автоперевода на канал: не реплаить при спаме подряд.
        self._last_auto: dict[int, float] = {}
        self._lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Пересланные сообщения (forward) тоже переводим: особых кейсов нет,
        # контент пересланного сообщения лежит в message.content.
        is_forward = bool(message.flags and message.flags.forwarded)

        # Автоперевод только в перечисленных каналах.
        if message.channel.id not in config.TRANSLATE_CHANNELS:
            return

        text = _message_text(message)
        if not text or len(text) < 2:
            return
        # Скипаем команды и сырые ссылки; пересланные посты не трогаем фильтром.
        if not is_forward and text.startswith(("http://", "https://", "!", "/", ".")):
            return

        now = time.monotonic()
        async with self._lock:
            last = self._last_auto.get(message.channel.id, 0)
            if now - last < 5:
                return
            self._last_auto[message.channel.id] = now

        translated = await async_translate_text(text, config.TRANSLATE_TARGET)
        if translated and translated.strip().lower() != text.lower():
            embed = discord.Embed(
                title=f"🌐 Перевод • {message.author.display_name}",
                description=translated,
                color=config.EMBED_COLOR,
            )
            files = _image_files(message)
            await message.reply(embed=embed, files=files or None, mention_author=False)


async def setup(bot: commands.Bot):
    bot.tree.add_command(translate_context)
    await bot.add_cog(TranslateCog(bot))