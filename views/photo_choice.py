import discord


class PhotoChoiceView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.channel = channel

    @discord.ui.button(label="Да", style=discord.ButtonStyle.success)
    async def photo_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from state import user_target_channel
        user_target_channel[interaction.user.id] = self.channel
        await interaction.response.send_message(
            "📸 Прикрепите фото к сообщению прямо в этот чат (через + в Discord). "
            "После отправки фото откроется кнопка публикации.",
            ephemeral=True,
        )

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.danger)
    async def photo_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from modals.send_message import SendMessageModal
        from state import user_attachments
        saved = user_attachments.get(interaction.user.id, [])
        await interaction.response.send_modal(SendMessageModal(self.channel, saved))
