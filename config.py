import json
import logging
import os
import discord
from dotenv import load_dotenv

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(override=True)

log = logging.getLogger("config")


def _int(name: str, default: int = 0) -> int:
    """Чтение int-переменной из .env без краша на нечисловом значении."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("Переменная %s=%r не является числом, использую %d", name, raw, default)
        return default


def _ints(name: str) -> list[int]:
    """Список int-переменной: нечисловые токены отбрасываются."""
    return [
        int(x)
        for x in os.getenv(name, "").replace(" ", "").split(",")
        if x.strip().isdigit()
    ]


TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = _int("GUILD_ID")

# Тикеты
TICKET_GUILD_ID = _int("TICKET_GUILD_ID", GUILD_ID)
TICKET_CATEGORY = _int("TICKET_CATEGORY")
TICKET_STAFF_ROLES = _ints("TICKET_STAFF_ROLES")
TICKET_LOG_CHANNEL = _int("TICKET_LOG_CHANNEL", 1545113128625246310)
TICKET_TRANSCRIPT_CHANNEL = _int("TICKET_TRANSCRIPT_CHANNEL")
ALLOWED_EVERYONE_OPEN = _int("TICKET_ALLOWED_EVERYONE_OPEN", 5)

# Голосовые
VC_TRIGGER_CHANNEL = _int("VC_TRIGGER_CHANNEL")
VC_CATEGORY = _int("VC_CATEGORY")
VC_CONTROL_CHANNEL = _int("VC_CONTROL_CHANNEL")

LOG_CHANNEL = _int("LOG_CHANNEL")

# Перевод
TRANSLATE_CHANNELS = _ints("TRANSLATE_CHANNELS")
TRANSLATE_TARGET = os.getenv("TRANSLATE_TARGET", "ru")

# Фон rank-карточки (путь к картинке; пусто = градиент)
RANK_BACKGROUND = os.getenv("RANK_BACKGROUND", "")

# Стримеры / Twitch
TWITCH_CHANNELS = [
    x.strip().lower().lstrip("@")
    for x in os.getenv("TWITCH_CHANNELS", "").split(",")
    if x.strip()
]
TWITCH_ANNOUNCE_CHANNEL = _int("TWITCH_ANNOUNCE_CHANNEL")
TWITCH_CHECK_INTERVAL = _int("TWITCH_CHECK_INTERVAL", 60)

# Пункт 6: зеркало чужого канала → наши каналы
# MIRROR_SOURCES = "chan_id@guild_id:dest_id,dest2; ..." но основной способ —
# через БД и слэш-команду, чтобы менять без правки кода.
MIRROR_ADD_COMMAND_USERS = _ints("MIRROR_ADMINS")

# Активности (роли за активность)
try:
    ACTIVITY_ROLES_CONFIG = json.loads(os.getenv("ACTIVITY_ROLES_CONFIG", "[]"))
except json.JSONDecodeError:
    ACTIVITY_ROLES_CONFIG = []
if not isinstance(ACTIVITY_ROLES_CONFIG, list):
    ACTIVITY_ROLES_CONFIG = []

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

EMBED_COLOR = discord.Color(0x5865F2)