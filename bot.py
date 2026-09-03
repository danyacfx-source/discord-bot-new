import asyncio
import logging
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import discord
from discord.ext import commands

import config
from database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

bot = commands.Bot(command_prefix="!", intents=config.intents, reconnect=True)


@bot.event
async def on_ready():
    guild = discord.Object(id=config.GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    logging.info("%s запущен! Коги загружены, команды синхронизированы для гильдии %s.", bot.user, config.GUILD_ID)


async def main():
    init_db()

    cogs = [
        "cogs.translate",
        "cogs.admin",
        "cogs.panel",
        "cogs.tickets",
        "cogs.temp_voice",
        "cogs.stats",
        "cogs.activity_roles",
    ]

    async with bot:
        for cog in cogs:
            try:
                await bot.load_extension(cog)
                logging.info("Загружен ког: %s", cog)
            except Exception as e:
                logging.error("Ошибка загрузки %s: %s", cog, e)

        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
