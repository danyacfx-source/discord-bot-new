import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import (
    get_twitch_channels,
    add_twitch_channel,
    remove_twitch_channel,
)
from twitch_api import fetch_stream, TwitchError

log = logging.getLogger(__name__)

LIVE_COLOR = discord.Color(0x9146FF)      # фиолетовый Twitch
OFFLINE_COLOR = discord.Color(0x5865F2)


class TwitchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._states: dict[str, bool] = {}
        self._live_messages: dict[str, discord.Message] = {}
        self.twitch_loop.start()

    def cog_unload(self):
        self.twitch_loop.cancel()

    @tasks.loop(seconds=config.TWITCH_CHECK_INTERVAL)
    async def twitch_loop(self):
        try:
            await self._tick()
        except TwitchError as e:
            log.warning("Twitch API error: %s", e)
        except Exception as e:
            log.warning("Twitch tick error: %s", e)

    @twitch_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
        # Первый прогон: фиксируем текущий статус, чтобы не спамить
        # стартами каналов, которые уже были в эфире до запуска бота.
        log.info("Инициализация статусов Twitch-каналов...")
        for login in config.TWITCH_CHANNELS:
            add_twitch_channel(login, 0)
        channel = self.bot.get_channel(config.TWITCH_ANNOUNCE_CHANNEL)
        for login in get_twitch_channels():
            try:
                stream = await fetch_stream(login)
                self._states[login] = stream.is_live
                if stream.is_live and channel is not None:
                    # Стрим уже шёл до запуска бота — создаём сообщение,
                    # чтобы дальше обновлять в нём количество зрителей.
                    msg = await channel.send(embed=self._live_embed(stream))
                    self._live_messages[login] = msg
            except TwitchError:
                pass
        log.info("Статусы инициализированы: %s", self._states)

    async def _tick(self):
        channel = self.bot.get_channel(config.TWITCH_ANNOUNCE_CHANNEL)
        if channel is None:
            log.warning("Канал %s не найден", config.TWITCH_ANNOUNCE_CHANNEL)
            return

        for login in get_twitch_channels():
            stream = await fetch_stream(login)
            was_live = self._states.get(login, False)
            live_msg = self._live_messages.get(login)

            if stream.is_live and not was_live:
                # Стрим только начался — постим новое сообщение.
                msg = await channel.send(embed=self._live_embed(stream))
                self._live_messages[login] = msg
            elif stream.is_live and was_live and live_msg is not None:
                # Стрим продолжается — обновляем количество зрителей.
                try:
                    await live_msg.edit(embed=self._live_embed(stream))
                except discord.NotFound:
                    self._live_messages.pop(login, None)
            elif not stream.is_live and was_live:
                await channel.send(embed=self._offline_embed(stream))
                self._live_messages.pop(login, None)

            self._states[login] = stream.is_live

    def _live_embed(self, stream) -> discord.Embed:
        embed = discord.Embed(
            title="🔴 Прямо в эфире!",
            description=f"**{stream.stream_title}**" if stream.stream_title else None,
            url=stream.url,
            color=LIVE_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=stream.display_name, url=stream.url)
        embed.add_field(name="🎮 Игра", value=stream.game, inline=True)
        embed.add_field(name="👥 Зрители", value=f"**{stream.viewers}**", inline=True)
        if stream.thumbnail:
            embed.set_image(url=stream.thumbnail)
        embed.set_footer(text=f"Twitch • {stream.login}")
        return embed

    def _offline_embed(self, stream) -> discord.Embed:
        embed = discord.Embed(
            title="Стрим закончился",
            description=f"[{stream.display_name}]({stream.url}) вернулся(ась) в оффлайн.",
            color=OFFLINE_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        return embed

    @app_commands.command(name="add_channel", description="Добавить Twitch-канал для отслеживания трансляций")
    @app_commands.describe(login="Логин канала на Twitch (например: f_a_n_e)")
    async def add_channel(self, interaction: discord.Interaction, login: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return

        login = login.strip().lower().lstrip("@")
        if not login or any(c.isspace() for c in login):
            await interaction.response.send_message("❌ Неверный логин.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            stream = await fetch_stream(login)
        except TwitchError as e:
            await interaction.followup.send(f"❌ Не удалось проверить канал: {e}", ephemeral=True)
            return

        if not stream.login:
            await interaction.followup.send("❌ Канал не найден на Twitch.", ephemeral=True)
            return

        added = add_twitch_channel(stream.login, interaction.user.id)
        if added:
            self._states[stream.login] = stream.is_live
            await interaction.followup.send(f"✅ Канал **{stream.login}** добавлен!", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ Канал **{stream.login}** уже отслеживается.", ephemeral=True)

    @app_commands.command(name="remove_channel", description="Убрать Twitch-канал из отслеживания")
    @app_commands.describe(login="Логин канала на Twitch")
    async def remove_channel(self, interaction: discord.Interaction, login: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return

        login = login.strip().lower().lstrip("@")
        removed = remove_twitch_channel(login)
        if removed:
            self._states.pop(login, None)
            await interaction.response.send_message(f"✅ Канал **{login}** удалён.", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ Канал **{login}** не отслеживается.", ephemeral=True)

    @app_commands.command(name="twitch_channels", description="Список отслеживаемых Twitch-каналов")
    async def twitch_channels(self, interaction: discord.Interaction):
        channels = get_twitch_channels()
        if not channels:
            await interaction.response.send_message("📭 Нет отслеживаемых каналов.", ephemeral=True)
            return

        lines = []
        for login in channels:
            live = self._states.get(login, False)
            icon = "🔴" if live else "⚫"
            lines.append(f"{icon} **{login}**")
        await interaction.response.send_message(
            f"**Отслеживаемые каналы ({len(channels)}):**\n" + "\n".join(lines),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchCog(bot))