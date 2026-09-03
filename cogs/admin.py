import discord
from discord import app_commands
from discord.ext import commands


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="announce", description="Отправить объявление от имени бота")
    @app_commands.describe(text="Текст объявления")
    async def announce(self, interaction: discord.Interaction, text: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return

        await interaction.channel.send(f"🐺 **WARDOGS RU**\n\n{text}")
        await interaction.response.send_message("✅ Объявление отправлено.", ephemeral=True)

    @app_commands.command(name="rules", description="Опубликовать правила WARDOGS RU")
    async def rules(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🐺 WARDOGS RU",
            description=(
                "## 📜 Правила сообщества\n\n"
                "Добро пожаловать в русскоязычное сообщество "
                "**WARDOGS RU!**\nЗдесь мы играем, общаемся и собираемся в отряды."
            ),
            color=discord.Color(0x5865F2),
        )

        rules_list = [
            ("🤝 1. Уважение", "Уважайте других участников.\nОскорбления, травля, унижение и провокации запрещены."),
            ("💬 2. Общение", "Спорить можно. Переходить на личности — нет."),
            ("🚫 3. Запрещённый контент", "NSFW, шок-контент, угрозы, распространение личных данных и незаконные материалы запрещены."),
            ("📢 4. Спам и реклама", "Запрещены флуд, спам и навязчивая реклама.\nРеклама разрешена только в соответствующих каналах."),
            ("🎮 5. WARDOGS", "Не выдавайте себя за администрацию сообщества или разработчиков игры."),
            ("🎙 6. Голосовые каналы", "Не мешайте другим участникам играть и общаться.\nНамеренный шум и провокации запрещены."),
            ("🛡 7. Администрация", "**Предупреждение → Мут → Кик → Временный бан → Перманентный бан**\n\nЗа серьёзные нарушения наказание может быть выдано сразу."),
            ("🐺 Главное правило", "**Мы здесь ради игры, общения и хорошей атмосферы.**\n\nДобро пожаловать в WARDOGS RU! 🐺"),
        ]

        for name, value in rules_list:
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text="WARDOGS RU • Русскоязычное сообщество")
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Правила опубликованы.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
