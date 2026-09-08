import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    create_giveaway,
    get_active_giveaways,
    get_giveaway,
    set_giveaway_done,
    add_participant,
    get_participants,
    get_participant_count,
    set_giveaway_message_id,
)


def _embed_for(g: dict) -> discord.Embed:
    end_dt = datetime.fromisoformat(g["ends_at"])
    ts = int(end_dt.timestamp())
    embed = discord.Embed(
        title=f"🎉 {g['prize']}",
        description=(
            "Нажми **🎉 Участвовать**, чтобы принять участие в розыгрыше!\n\n"
            f"⏰ До окончания: <t:{ts}:R>\n"
            f"📅 Завершится: <t:{ts}:f>\n"
            f"🎁 Кол-во победителей: **{g['winners']}**\n"
            f"👑 Устроил: <@{g['created_by']}>"
        ),
        color=discord.Color.green(),
    )
    count = get_participant_count(g["id"])
    embed.set_footer(text=f"Участников: {count} • ID розыгрыша: {g['id']}")
    return embed


class JoinButton(discord.ui.Button):
    def __init__(self, giveaway_id: int):
        super().__init__(
            label="🎉 Участвовать",
            style=discord.ButtonStyle.success,
            custom_id=f"gwa_join:{giveaway_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.on_join(interaction)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.add_item(JoinButton(giveaway_id))

    async def on_join(self, interaction: discord.Interaction):
        gid = self.giveaway_id
        g = get_giveaway(gid)
        if g is None or g["done"]:
            await interaction.response.send_message("❌ Этот розыгрыш уже завершён.", ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        if datetime.fromisoformat(g["ends_at"]) <= now:
            await interaction.response.send_message("❌ Розыгрыш уже закончился.", ephemeral=True)
            return
        entered = add_participant(self.giveaway_id, interaction.user.id)
        if not entered:
            await interaction.response.send_message("ℹ️ Ты уже участвуешь в этом розыгрыше!", ephemeral=True)
            return
        try:
            await interaction.message.edit(embed=_embed_for(g))
        except Exception:
            pass
        await interaction.response.send_message("✅ Ты участвуешь! Удачи! 🍀", ephemeral=True)


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._check_task: asyncio.Task | None = None
        self._views: dict[int, GiveawayView] = {}

    # ---------- Автоподведение итогов ----------

    async def cog_load(self):
        for g in get_active_giveaways():
            view = GiveawayView(g["id"])
            self._views[g["id"]] = view
            self.bot.add_view(view)
        self._check_task = asyncio.create_task(self._check_loop())

    async def _check_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self._check_giveaways()
            except Exception:
                pass
            await asyncio.sleep(15)

    async def _finish(self, g: dict):
        participants = get_participants(g["id"])
        winners_to_pick = min(int(g["winners"]), len(participants))
        winners = random.sample(participants, winners_to_pick) if winners_to_pick else []

        channel = self.bot.get_channel(int(g["channel_id"]))
        if channel is None:
            set_giveaway_done(g["id"])
            return

        end_dt = datetime.fromisoformat(g["ends_at"])
        embed = discord.Embed(
            title=f"🎉 Розыгрыш завершён: {g['prize']}",
            description=f"📅 Завершён: <t:{int(end_dt.timestamp())}:f>",
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"Участников было: {len(participants)}")

        if winners:
            win_mentions = " ".join(f"<@{w}>" for w in winners)
            if len(winners) > 1:
                desc = f"Победители: {win_mentions}\n\n🎁 Поздравляем! Вы выиграли **{g['prize']}**!"
            else:
                desc = f"Победитель: {win_mentions}\n\n🎁 Поздравляем! Ты выиграл **{g['prize']}**!"
            embed.description = desc
            embed.color = discord.Color.gold()
        else:
            embed.description = "😔 В розыгрыше никто не участвовал. Победитель не выбран."

        await channel.send(embed=embed)
        for w in winners:
            try:
                user = await self.bot.fetch_user(w)
                await user.send(f"🎉 Поздравляем, **{user.display_name}**! Ты выиграл **{g['prize']}** в розыгрыше на сервере **{channel.guild.name}**!")
            except Exception:
                pass

        try:
            msg = await channel.fetch_message(int(g["message_id"]))
            await msg.edit(view=None)
        except Exception:
            pass

        set_giveaway_done(g["id"])

    async def _check_giveaways(self):
        now = datetime.now(timezone.utc)
        for g in get_active_giveaways():
            end_dt = datetime.fromisoformat(g["ends_at"])
            if end_dt <= now:
                await self._finish(g)

    # ---------- Команды ----------

    giveaway = app_commands.Group(name="giveaway", description="Розыгрыши", guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    @giveaway.command(name="create", description="Создать розыгрыш")
    @app_commands.describe(
        prize="Что разыгрываем",
        length="Длительность (число)",
        unit="Единица времени: минуты / часы / дни",
        winners="Количество призовых мест (победителей)",
        channel="Где создать розыгрыш (по умолчанию текущий канал)",
    )
    @app_commands.choices(unit=[
        app_commands.Choice(name="минуты", value="minutes"),
        app_commands.Choice(name="часы", value="hours"),
        app_commands.Choice(name="дни", value="days"),
    ])
    async def giveaway_create(
        self,
        interaction: discord.Interaction,
        prize: str,
        length: int,
        winners: int,
        unit: app_commands.Choice[str] = None,
        channel: discord.TextChannel = None,
    ):
        if unit is None:
            unit = app_commands.Choice(name="часы", value="hours")
        length = max(1, abs(length))
        winners = max(1, min(winners, 50))
        td = timedelta(
            minutes=length if unit.value == "minutes" else 0,
            hours=length if unit.value == "hours" else 0,
            days=length if unit.value == "days" else 0,
        )
        if td.total_seconds() <= 0:
            td = timedelta(hours=length)
        td = min(td, timedelta(days=365))
        ends_at = (datetime.now(timezone.utc) + td).isoformat()
        gid = create_giveaway(
            channel_id=(channel or interaction.channel).id,
            guild_id=interaction.guild.id,
            prize=prize,
            ends_at=ends_at,
            winners=winners,
            created_by=interaction.user.id,
        )
        g = get_giveaway(gid)

        target = channel or interaction.channel
        view = GiveawayView(gid)
        self._views[gid] = view

        if interaction.channel == target:
            await interaction.response.defer(ephemeral=True)
            sent_msg = await target.send(embed=_embed_for(g), view=view)
        else:
            await interaction.response.send_message(f"✅ Розыгрыш создан в {target.mention}!", ephemeral=True)
            sent_msg = await target.send(embed=_embed_for(g), view=view)

        set_giveaway_message_id(gid, sent_msg.id)

    @giveaway.command(name="end", description="Досрочно завершить розыгрыш (выбрать победителя сейчас)")
    @app_commands.describe(giveaway_id="ID розыгрыша (внизу сообщения розыгрыша)")
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: int):
        g = get_giveaway(giveaway_id)
        if g is None:
            await interaction.response.send_message("❌ Розыгрыш не найден.", ephemeral=True)
            return
        if g["done"]:
            await interaction.response.send_message("ℹ️ Розыгрыш уже завершён.", ephemeral=True)
            return
        await interaction.response.send_message("⏳ Завершаю розыгрыш и выбираю победителя...", ephemeral=True)
        set_giveaway_done(g["id"])
        await self._finish(g)

    @giveaway.command(name="list", description="Список активных розыгрышей")
    async def giveaway_list(self, interaction: discord.Interaction):
        gws = get_active_giveaways()
        if not gws:
            await interaction.response.send_message("📭 Активных розыгрышей нет.", ephemeral=True)
            return
        lines = []
        for g in gws:
            end_dt = datetime.fromisoformat(g["ends_at"])
            ts = int(end_dt.timestamp())
            count = get_participant_count(g["id"])
            lines.append(f"**{g['id']}.** {g['prize']} — <t:{ts}:R> • 🎁 {g['winners']} • 👥 {count}")
        await interaction.response.send_message("**Активные розыгрыши:**\n" + "\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))