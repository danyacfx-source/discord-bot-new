import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord


class ChannelSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild, page: int = 0):
        super().__init__(timeout=60)
        self.guild = guild
        self.page = page

        all_channels = guild.text_channels
        start = page * 25
        end = start + 25
        current = all_channels[start:end]

        options = [
            discord.SelectOption(label=f"#{ch.name}", value=str(ch.id))
            for ch in current
        ]

        total_pages = max(1, (len(all_channels) - 1) // 25 + 1)
        placeholder = f"Выбери канал (стр. {page + 1}/{total_pages})..." if total_pages > 1 else "Выбери канал..."

        select = discord.ui.Select(placeholder=placeholder, options=options)
        select.callback = self._on_select
        self.add_item(select)

        if page > 0:
            btn = discord.ui.button(label="◀ Назад", style=discord.ButtonStyle.gray)
            btn.callback = self._prev
            self.add_item(btn)

        if end < len(all_channels):
            btn = discord.ui.button(label="Вперед ▶", style=discord.ButtonStyle.gray)
            btn.callback = self._next
            self.add_item(btn)

    async def _prev(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSelectView(self.guild, self.page - 1))

    async def _next(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSelectView(self.guild, self.page + 1))

    async def _on_select(self, interaction: discord.Interaction):
        from views.photo_choice import PhotoChoiceView
        channel_id = int(interaction.data["values"][0])
        channel = interaction.client.get_channel(channel_id)
        await interaction.response.send_message(
            "**Шаг 3:** Вы хотите добавить фото к сообщению?",
            view=PhotoChoiceView(channel),
            ephemeral=True,
        )
