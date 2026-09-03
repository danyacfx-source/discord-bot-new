import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord


class GuildSelectView(discord.ui.View):
    def __init__(self, guilds: list[discord.Guild], page: int = 0):
        super().__init__(timeout=60)
        self.guilds = guilds
        self.page = page

        start = page * 25
        end = start + 25
        current = guilds[start:end]

        options = [
            discord.SelectOption(label=g.name, value=str(g.id))
            for g in current
        ]

        total_pages = max(1, (len(guilds) - 1) // 25 + 1)
        placeholder = f"Выбери сервер (стр. {page + 1}/{total_pages})..." if total_pages > 1 else "Выбери сервер..."

        select = discord.ui.Select(placeholder=placeholder, options=options)
        select.callback = self._on_select
        self.add_item(select)

        if page > 0:
            btn = discord.ui.button(label="◀ Назад", style=discord.ButtonStyle.gray)
            btn.callback = self._prev
            self.add_item(btn)

        if end < len(guilds):
            btn = discord.ui.button(label="Вперед ▶", style=discord.ButtonStyle.gray)
            btn.callback = self._next
            self.add_item(btn)

    async def _prev(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSelectView(self.guilds, self.page - 1))

    async def _next(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSelectView(self.guilds, self.page + 1))

    async def _on_select(self, interaction: discord.Interaction):
        from views.channel_select import ChannelSelectView
        guild_id = int(interaction.data["values"][0])
        guild = interaction.client.get_guild(guild_id)
        await interaction.response.send_message(
            f"**Шаг 2:** Выбери канал на сервере {guild.name}:",
            view=ChannelSelectView(guild),
            ephemeral=True,
        )
