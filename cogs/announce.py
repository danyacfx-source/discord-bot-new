import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    clear_announce_channel,
    get_announce_channel,
    set_announce_channel,
)


class GuildSelectView(discord.ui.View):
    def __init__(self, guilds: list[discord.Guild]):
        super().__init__(timeout=120)
        options = [
            discord.SelectOption(label=g.name, value=str(g.id))
            for g in guilds[:25]
        ]
        select = discord.ui.Select(placeholder="Выберите сервер...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        guild_id = int(interaction.data["values"][0])
        guild = interaction.client.get_guild(guild_id)
        await interaction.response.send_message(
            f"**Шаг 2:** Выберите канал в **{guild.name}**:",
            view=ChannelSelectView(guild),
        )


class ChannelSelectView(discord.ui.View):
    CHANNELS_PER_PAGE = 24

    def __init__(self, guild: discord.Guild, page: int = 0):
        super().__init__(timeout=120)
        self.guild = guild
        self.channels = list(guild.text_channels)
        if self.channels:
            self.page = page
            self._pages = max(1, -(-len(self.channels) // self.CHANNELS_PER_PAGE))
        else:
            self.page = 0
            self._pages = 1
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        options = []
        if self.channels:
            start = self.page * self.CHANNELS_PER_PAGE
            chunk = self.channels[start : start + self.CHANNELS_PER_PAGE]
            options = [
                discord.SelectOption(label=f"#{ch.name}", value=str(ch.id))
                for ch in chunk
            ]
            select = discord.ui.Select(placeholder="Выберите канал...", options=options)
        else:
            select = discord.ui.Select(
                placeholder="Нет каналов на этом сервере",
                options=[discord.SelectOption(label="Нет каналов", value="none")],
                disabled=True,
            )
        select.callback = self._on_select
        self.add_item(select)

        prev = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
        )
        prev.callback = self._on_prev
        self.add_item(prev)

        counter = discord.ui.Button(
            label=f"{self.page + 1} / {self._pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
        self.add_item(counter)

        nxt = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self._pages - 1),
        )
        nxt.callback = self._on_next
        self.add_item(nxt)

    async def _on_prev(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _on_next(self, interaction: discord.Interaction):
        if self.page < self._pages - 1:
            self.page += 1
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _on_select(self, interaction: discord.Interaction):
        channel_id = int(interaction.data["values"][0])
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            return await interaction.response.send_message("❌ Канал не найден.", ephemeral=True)
        # Запоминаем канал в БД: persistent-кнопка «Отправить» должна пережить рестарт.
        set_announce_channel(interaction.user.id, channel.id, interaction.guild.id)
        await interaction.response.send_message(
            f"**Шаг 3:** Напишите текст **в этот личный чат** и/или прикрепите "
            f"фото/видео/GIF файлом, затем нажмите кнопку.\n📍 Канал: **#{channel.name}**",
            view=ChannelReadyView(channel),
        )


class ChannelReadyView(discord.ui.View):
    """Persistent-кнопка «Отправить». После рестарта пересоздаётся в on_ready
    с channel=None, а целевой канал достаётся из БД по user_id."""

    def __init__(self, channel: discord.TextChannel | None = None):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="🚀 Отправить", style=discord.ButtonStyle.green, custom_id="ann2_send")
    async def send_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = self.channel
        if channel is None:
            saved = get_announce_channel(interaction.user.id)
            if saved:
                guild = interaction.client.get_guild(saved["guild_id"])
                channel = guild.get_channel(saved["channel_id"]) if guild else None
        if channel is None:
            clear_announce_channel(interaction.user.id)
            return await interaction.response.send_message(
                "❌ Канал не найден. Начните заново: напишите «старт» в личку бота.",
                ephemeral=True,
            )
        await interaction.response.send_modal(SendMessageModal(channel))


class SendMessageModal(discord.ui.Modal, title="Отправка сообщения"):
    text = discord.ui.TextInput(
        label="Текст (если не написали в чате)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            content = self.text.value.strip() if self.text.value else None
            files = []
            fallback = None
            # Ищем последнее сообщение с вложениями в этом ЛС.
            async for msg in interaction.channel.history(limit=10):
                if msg.attachments:
                    for att in msg.attachments:
                        files.append(await att.to_file())
                    fallback = msg.content.strip()
                    break

            if not content and fallback:
                content = fallback
            if not content and not files:
                return await interaction.response.send_message(
                    "❌ Пустое сообщение — напишите текст или прикрепите файл.", ephemeral=True
                )

            await self.channel.send(content=content, files=files if files else None)
            await interaction.response.send_message(
                f"✅ Отправлено в **#{self.channel.name}**.", ephemeral=True
            )
            clear_announce_channel(interaction.user.id)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)


class AnnounceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _admin_guilds(self, user_id: int) -> list[discord.Guild]:
        out = []
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if not member:
                continue
            if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
                out.append(guild)
        return out

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.DMChannel) or message.author.bot:
            return
        text = message.content.strip()
        if text.lower() in ("старт", "start", "/start"):
            guilds = self._admin_guilds(message.author.id)
            if not guilds:
                return await message.channel.send("❌ Нет прав администратора ни на одном сервере!")
            await message.channel.send(
                "⚙️ **Панель отправки сообщений**\n**Шаг 1:** Выберите сервер:",
                view=GuildSelectView(guilds),
            )

    @app_commands.command(name="announce", description="Отправить объявление от имени бота в канал")
    @app_commands.describe(channel="Канал (по умолчанию текущий)", text="Текст объявления")
    @app_commands.guild_only()
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel = None, text: str = None):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        target = channel or interaction.channel
        if not text:
            return await interaction.response.send_message("❌ Укажите текст объявления.", ephemeral=True)
        await target.send(f"🐺 **WARDOGS**\n\n{text}")
        await interaction.response.send_message(f"✅ Отправлено в {target.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AnnounceCog(bot))