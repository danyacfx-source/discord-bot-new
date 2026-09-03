import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord


class SendMessageModal(discord.ui.Modal, title="Отправка сообщения"):
    message_text = discord.ui.TextInput(
        label="Текст сообщения (необязательно)",
        style=discord.TextStyle.paragraph,
        placeholder="Введите текст или оставьте пустым, если отправляете только фото...",
        required=False,
        max_length=2000,
    )

    def __init__(self, channel: discord.TextChannel, attachments: list = None):
        super().__init__()
        self.channel = channel
        self.attachments = attachments or []

    async def on_submit(self, interaction: discord.Interaction):
        from state import user_attachments, user_target_channel

        try:
            files = [await att.to_file() for att in self.attachments]
            content = self.message_text.value.strip() if self.message_text.value else None

            if not content and not files:
                await interaction.response.send_message(
                    "❌ Сообщение не может быть пустым!", ephemeral=True
                )
                return

            await self.channel.send(content=content, files=files)
            user_attachments.pop(interaction.user.id, None)
            user_target_channel.pop(interaction.user.id, None)

            await interaction.response.send_message(
                f"✅ Сообщение отправлено в #{self.channel.name}!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Не удалось отправить: {e}", ephemeral=True
            )
