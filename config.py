import json
import os
import discord
from dotenv import load_dotenv

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(override=True)

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

TICKET_CATEGORY = int(os.getenv("TICKET_CATEGORY", "0"))
TICKET_STAFF_ROLES = [
    int(x) for x in os.getenv("TICKET_STAFF_ROLES", "").replace(" ", "").split(",") if x.strip().isdigit()
]
TICKET_LOG_CHANNEL = int(os.getenv("TICKET_LOG_CHANNEL", "0"))
TICKET_TRANSCRIPT_CHANNEL = int(os.getenv("TICKET_TRANSCRIPT_CHANNEL", "0"))

VC_TRIGGER_CHANNEL = int(os.getenv("VC_TRIGGER_CHANNEL", "0"))
VC_CATEGORY = int(os.getenv("VC_CATEGORY", "0"))
VC_CONTROL_CHANNEL = int(os.getenv("VC_CONTROL_CHANNEL", "0"))

LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "0"))

try:
    ACTIVITY_ROLES_CONFIG = json.loads(os.getenv("ACTIVITY_ROLES_CONFIG", "[]"))
except json.JSONDecodeError:
    ACTIVITY_ROLES_CONFIG = []

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

EMBED_COLOR = discord.Color(0x5865F2)
