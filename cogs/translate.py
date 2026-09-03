import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord import app_commands
from discord.ext import commands

from translator import async_translate_text
from state import user_attachments, user_target_channel
from views import GuildSelectView
from modals import SendMessageModal


class TranslateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.context_menu(name="Перевести")
    async def translate_context(self, interaction: discord.Interaction, message: discord.Message):
        text = message.content.strip()
        if not text:
            await interaction.response.send_message(
                "❌ Сообщение не содержит текста.", ephemeral=True
            )
            return

        translated = await async_translate_text(text, "ru")
        if not translated:
            await interaction.response.send_message(
                "❌ Не удалось перевести.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🌐 Перевод • {message.author.display_name}",
            description=translated,
            color=discord.Color(0x5865F2),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        text = message.content.strip()

        if isinstance(message.channel, discord.DMChannel):
            await self._handle_dm(message, text)
            return

        if not text or len(text) < 2:
            return
        if text.startswith(("http://", "https://", "!", "/", ".")):
            return

        translated = await async_translate_text(text, "ru")
        if translated and translated.strip().lower() != text.lower():
            embed = discord.Embed(
                title=f"🌐 Перевод • {message.author.display_name}",
                description=translated,
                color=discord.Color(0x5865F2),
            )
            await message.reply(embed=embed, mention_author=False)

    async def _handle_dm(self, message: discord.Message, text: str):
        attachments = list(message.attachments)
        uid = message.author.id

        if uid in user_target_channel and attachments:
            channel = user_target_channel.pop(uid)
            user_attachments[uid] = attachments

            view = discord.ui.View()
            btn = discord.ui.Button(label="Отправить", style=discord.ButtonStyle.primary)

            async def cb(interaction: discord.Interaction):
                await interaction.response.send_modal(SendMessageModal(channel, attachments))

            btn.callback = cb
            view.add_item(btn)

            await message.channel.send(
                f"✅ Фото прикреплено: **{len(attachments)} шт.** Нажмите кнопку для отправки:",
                view=view,
            )
            return

        if text.lower() in ("старт", "start") or (attachments and uid not in user_target_channel):
            admin_guilds = []
            for guild in self.bot.guilds:
                member = guild.get_member(uid)
                if not member:
                    try:
                        member = await guild.fetch_member(uid)
                    except Exception:
                        continue
                if member and (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
                    admin_guilds.append(guild)

            if not admin_guilds:
                await message.channel.send("❌ Нет прав администратора ни на одном сервере!")
                return

            if attachments:
                user_attachments[uid] = attachments

            await message.channel.send(
                "⚙️ **Панель отправки сообщений**\n**Шаг 1:** Выбери сервер:",
                view=GuildSelectView(admin_guilds),
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(TranslateCog(bot))
