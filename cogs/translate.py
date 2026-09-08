import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    text = message.content.strip()
    if not text:
        await interaction.response.send_message("❌ Сообщение без текста.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    translated = await async_translate_text(text, config.TRANSLATE_TARGET)
    if not translated:
        await interaction.followup.send("❌ Не удалось перевести.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🌐 Перевод • {message.author.display_name}",
        description=translated,
        color=config.EMBED_COLOR,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


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

        text = message.content.strip()

        # Автоперевод только в перечисленных каналах.
        if message.channel.id not in config.TRANSLATE_CHANNELS:
            return
        if not text or len(text) < 2:
            return
        if text.startswith(("http://", "https://", "!", "/", ".")):
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
            await message.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    bot.tree.add_command(translate_context)
    await bot.add_cog(TranslateCog(bot))