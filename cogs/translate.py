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

    embed = _translation_embed(message, translated)
    image_url = _embed_image_url(message)
    files = _attachment_files(message)
    if files:
        await interaction.followup.send(embed=embed, files=files)
    else:
        if image_url:
            embed.set_image(url=image_url)
        await interaction.followup.send(embed=embed)


def _message_text(message: discord.Message) -> str:
    """Весь текст сообщения с сохранением структуры: content + все embed'ы."""
    parts: list[str] = []

    if message.content and message.content.strip():
        parts.append(message.content.strip())

    for emb in message.embeds:
        emb_parts: list[str] = []
        if emb.title:
            emb_parts.append(f"**{emb.title}**")
        if emb.description:
            emb_parts.append(emb.description.strip())
        for field in emb.fields:
            if field.name or field.value:
                emb_parts.append(f"**{field.name}**: {field.value}".strip())
        if emb_parts:
            parts.append("\n\n".join(emb_parts))

    return "\n\n".join(parts).strip()


def _translation_embed(message: discord.Message, translated: str) -> discord.Embed:
    embed = discord.Embed(
        description=translated,
        color=config.EMBED_COLOR,
    )
    return embed


def _attachment_files(message: discord.Message) -> list[discord.Attachment]:
    """Вложения сообщения, чтобы пересылать вместе с переводом без потерь."""
    return list(message.attachments)[:10]


def _embed_image_url(message: discord.Message) -> str | None:
    """Картинка из embed'а (Steam-фиды и т.п.), если вложений нет."""
    for emb in message.embeds:
        if emb.image and emb.image.url:
            return emb.image.url
        if emb.thumbnail and emb.thumbnail.url:
            return emb.thumbnail.url
    return None


class TranslateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Не трогаем собственные ответы-переводы, чтобы не было цикла.
        if message.author.id == self.bot.user.id:
            return

        # Автоперевод только в перечисленных каналах.
        if message.channel.id not in config.TRANSLATE_CHANNELS:
            return

        text = _message_text(message)
        if not text:
            return

        translated = await async_translate_text(text, config.TRANSLATE_TARGET)
        if not translated:
            return
        # Сообщение уже на языке назначения — дублировать не нужно.
        if translated.strip().lower() == text.strip().lower():
            return

        embed = _translation_embed(message, translated)
        image_url = _embed_image_url(message)
        files = _attachment_files(message)
        if files:
            await message.channel.send(embed=embed, files=files)
        else:
            if image_url:
                embed.set_image(url=image_url)
            await message.channel.send(embed=embed)


async def setup(bot: commands.Bot):
    bot.tree.add_command(translate_context)
    await bot.add_cog(TranslateCog(bot))