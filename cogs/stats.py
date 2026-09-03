import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord import app_commands
from discord.ext import commands

from database import get_conn, format_duration


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_sessions: dict[int, dict] = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        conn = get_conn()
        now = discord.utils.utcnow()
        now_iso = now.isoformat()

        if before.channel is None and after.channel is not None:
            conn.execute(
                "INSERT INTO member_stats (user_id, messages, voice_seconds, voice_joins) "
                "VALUES (?, 0, 0, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET voice_joins = voice_joins + 1",
                (member.id,),
            )
            self._voice_sessions[member.id] = {"start": now, "channel": after.channel.name}

        elif before.channel is not None and after.channel is None:
            if member.id in self._voice_sessions:
                session = self._voice_sessions.pop(member.id)
                elapsed = (now - session["start"]).total_seconds()
                if elapsed > 5:
                    secs = int(elapsed)
                    conn.execute(
                        "UPDATE member_stats SET voice_seconds = voice_seconds + ? WHERE user_id = ?",
                        (secs, member.id),
                    )
                    conn.execute(
                        "INSERT INTO voice_sessions (user_id, channel, start, end, seconds) VALUES (?, ?, ?, ?, ?)",
                        (member.id, session["channel"], session["start"].isoformat(), now_iso, secs),
                    )

        elif before.channel and after.channel and before.channel.id != after.channel.id:
            if member.id in self._voice_sessions:
                session = self._voice_sessions.pop(member.id)
                elapsed = (now - session["start"]).total_seconds()
                if elapsed > 5:
                    secs = int(elapsed)
                    conn.execute(
                        "UPDATE member_stats SET voice_seconds = voice_seconds + ? WHERE user_id = ?",
                        (secs, member.id),
                    )
                    conn.execute(
                        "INSERT INTO voice_sessions (user_id, channel, start, end, seconds) VALUES (?, ?, ?, ?, ?)",
                        (member.id, session["channel"], session["start"].isoformat(), now_iso, secs),
                    )
            self._voice_sessions[member.id] = {"start": now, "channel": after.channel.name}

        conn.commit()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        conn = get_conn()
        conn.execute(
            "INSERT INTO member_stats (user_id, messages, voice_seconds, voice_joins) "
            "VALUES (?, 1, 0, 0) "
            "ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1",
            (message.author.id,),
        )
        conn.commit()

    @app_commands.command(name="участник", description="Статистика участника")
    @app_commands.describe(user="Участник (по умолчанию ты)")
    async def user_info(self, interaction: discord.Interaction, user: discord.Member = None):
        member = user or interaction.user
        conn = get_conn()
        row = conn.execute(
            "SELECT messages, voice_seconds, voice_joins FROM member_stats WHERE user_id = ?",
            (member.id,),
        ).fetchone()

        embed = discord.Embed(
            title=f"👤 {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if row:
            embed.add_field(name="💬 Сообщения", value=f"**{row['messages']}**", inline=True)
            embed.add_field(name="🔊 В голосе", value=f"**{format_duration(row['voice_seconds'])}**", inline=True)
            embed.add_field(name="🚪 Заходов", value=f"**{row['voice_joins']}**", inline=True)
        else:
            embed.description = "_Статистика пока пуста._"

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="топ_актив", description="Топ участников по активности")
    @app_commands.choices(metric=[
        app_commands.Choice(name="Сообщения", value="messages"),
        app_commands.Choice(name="Голосовое время", value="voice"),
        app_commands.Choice(name="Заходы в войс", value="joins"),
    ])
    async def top_active(self, interaction: discord.Interaction, metric: app_commands.Choice[str]):
        await interaction.response.defer()

        col_map = {"messages": "messages", "voice": "voice_seconds", "joins": "voice_joins"}
        title_map = {
            "messages": "🏆 Топ по сообщениям",
            "voice": "🏆 Топ по голосовому времени",
            "joins": "🏆 Топ по заходам в войс",
        }
        col = col_map[metric.value]
        conn = get_conn()
        rows = conn.execute(
            f"SELECT user_id, {col} FROM member_stats WHERE {col} > 0 ORDER BY {col} DESC LIMIT 15",
        ).fetchall()

        if not rows:
            return await interaction.followup.send("Статистика пуста.")

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"User {row['user_id']}"
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            val = format_duration(row[col]) if metric.value == "voice" else str(row[col])
            lines.append(f"{medal} {name} — {val}")

        embed = discord.Embed(
            title=title_map[metric.value],
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
