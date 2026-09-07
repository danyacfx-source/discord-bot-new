import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wardogs.db")
_local = threading.local()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_FILE, check_same_thread=False, isolation_level=None)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS member_stats (
            user_id INTEGER PRIMARY KEY,
            messages INTEGER DEFAULT 0,
            voice_seconds INTEGER DEFAULT 0,
            voice_joins INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel TEXT,
            start TEXT,
            end TEXT,
            seconds INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_voice_sessions_user ON voice_sessions(user_id);

        CREATE TABLE IF NOT EXISTS tickets (
            number INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER,
            ticket_type TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            created_at TEXT,
            closed_at TEXT,
            closed_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);
        CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);

        CREATE TABLE IF NOT EXISTS activity_roles_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            granted INTEGER DEFAULT 1,
            timestamp TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_arl_user ON activity_roles_log(user_id);

        CREATE TABLE IF NOT EXISTS twitch_channels (
            login TEXT PRIMARY KEY,
            added_by INTEGER NOT NULL,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_xp (
            user_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            last_message_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_user_xp_guild ON user_xp(guild_id);

        CREATE TABLE IF NOT EXISTS backgrounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            cx INTEGER DEFAULT 125,
            cy INTEGER DEFAULT 135,
            radius INTEGER DEFAULT 75
        );

        CREATE TABLE IF NOT EXISTS log_channels (
            log_type TEXT PRIMARY KEY,
            channel_id INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS log_sent (
            fingerprint TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL
        );
    """)
    conn.commit()

def get_twitch_channels() -> list[str]:
    """Список отслеживаемых Twitch-каналов."""
    conn = get_conn()
    rows = conn.execute("SELECT login FROM twitch_channels ORDER BY login").fetchall()
    return [r["login"] for r in rows]

def add_twitch_channel(login: str, added_by: int) -> bool:
    """Добавить канал. Вернёт False, если такой уже есть."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO twitch_channels (login, added_by, added_at) VALUES (?, ?, ?)",
        (login, added_by, _utcnow()),
    )
    conn.commit()
    return cur.rowcount > 0

def remove_twitch_channel(login: str) -> bool:
    """Удалить канал. Вернёт True, если он был."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM twitch_channels WHERE login = ?", (login,))
    conn.commit()
    return cur.rowcount > 0


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек."
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours == 0:
        return f"{minutes} мин."
    return f"{hours} ч. {minutes} мин."


# --- XP / уровни ---

def xp_needed_for_level(level: int) -> int:
    """Суммарный XP, необходимый для достижения уровня level."""
    total = 0
    for l in range(1, level):
        total += 100 + 50 * (l - 1)
    return total


def level_from_xp(xp: int) -> int:
    """Текущий уровень по суммарному XP."""
    level = 1
    while xp >= xp_needed_for_level(level + 1):
        level += 1
    return level


def xp_progress(xp: int, level: int) -> tuple[int, int]:
    """(Прогресс уровня, нужно для следующего уровня)."""
    current = xp_needed_for_level(level)
    nxt = xp_needed_for_level(level + 1)
    return xp - current, nxt - current


def ensure_user_xp(user_id: int, guild_id: int):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO user_xp (user_id, guild_id) VALUES (?, ?)",
        (user_id, guild_id),
    )
    conn.commit()


def add_xp(user_id: int, guild_id: int, amount: int) -> tuple[int, int]:
    """Добавить XP. Возвращает (было_уровней, стало_уровней)."""
    conn = get_conn()
    ensure_user_xp(user_id, guild_id)
    row = conn.execute(
        "SELECT xp, level FROM user_xp WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    old_level = row["level"]
    new_xp = row["xp"] + amount
    new_level = level_from_xp(new_xp)
    conn.execute(
        "UPDATE user_xp SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
        (new_xp, new_level, user_id, guild_id),
    )
    conn.commit()
    return old_level, new_level


def get_user_xp(user_id: int, guild_id: int) -> tuple[int, int] | None:
    """(xp, level) или None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT xp, level FROM user_xp WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    if not row:
        return None
    return row["xp"], row["level"]


def set_last_message(user_id: int, guild_id: int):
    conn = get_conn()
    ensure_user_xp(user_id, guild_id)
    conn.execute(
        "UPDATE user_xp SET last_message_at = ? WHERE user_id = ? AND guild_id = ?",
        (_utcnow(), user_id, guild_id),
    )
    conn.commit()


def can_get_message_xp(user_id: int, guild_id: int, cooldown_seconds: int = 60) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_message_at FROM user_xp WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id),
    ).fetchone()
    if not row or not row["last_message_at"]:
        return True
    last = datetime.fromisoformat(row["last_message_at"])
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() >= cooldown_seconds


def get_leaderboard(guild_id: int, limit: int = 15) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, xp, level FROM user_xp WHERE guild_id = ? "
        "ORDER BY xp DESC LIMIT ?",
        (guild_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_xp_rank(user_id: int, guild_id: int) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM user_xp WHERE guild_id = ? AND xp > "
        "(SELECT COALESCE(xp,0) FROM user_xp WHERE user_id = ? AND guild_id = ?)",
        (guild_id, user_id, guild_id),
    ).fetchone()
    return (row["c"] if row else 0) + 1


# --- Backgrounds (фоны rank-карточки) ---

def add_background(path: str, added_by: int) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO backgrounds (path, added_by, added_at) VALUES (?, ?, ?)",
        (path, added_by, _utcnow()),
    )
    conn.commit()
    return cur.rowcount > 0


def get_backgrounds() -> list[str]:
    conn = get_conn()
    return [r["path"] for r in conn.execute("SELECT path FROM backgrounds ORDER BY id").fetchall()]


def get_random_bg() -> dict | None:
    """Случайный фон с позицией аватара. Возвращает {path, cx, cy, radius} или None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT path, cx, cy, radius FROM backgrounds ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def set_bg_pos(rid: int, cx: int, cy: int, radius: int) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE backgrounds SET cx=?, cy=?, radius=? WHERE id=?",
        (cx, cy, radius, rid),
    )
    conn.commit()
    return cur.rowcount > 0


def remove_background(rid: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM backgrounds WHERE id = ?", (rid,))
    conn.commit()
    return cur.rowcount > 0


def clear_backgrounds() -> int:
    conn = get_conn()
    cur = conn.execute("DELETE FROM backgrounds")
    conn.commit()
    return cur.rowcount


# --- Log channels ---

def set_log_channel(log_type: str, channel_id: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO log_channels (log_type, channel_id) VALUES (?, ?) "
        "ON CONFLICT(log_type) DO UPDATE SET channel_id = excluded.channel_id",
        (log_type, channel_id),
    )
    conn.commit()


def get_log_channel(log_type: str) -> int | None:
    conn = get_conn()
    row = conn.execute("SELECT channel_id FROM log_channels WHERE log_type = ?", (log_type,)).fetchone()
    return row["channel_id"] if row else None


def get_all_log_channels() -> dict[str, int]:
    conn = get_conn()
    return {r["log_type"]: r["channel_id"] for r in conn.execute("SELECT * FROM log_channels").fetchall()}


def remove_log_channel(log_type: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM log_channels WHERE log_type = ?", (log_type,))
    conn.commit()
    return cur.rowcount > 0


# --- Anti-duplicate for log embeds ---

_claim_memory: dict[str, float] = {}

import time as _time


def _time_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - __import__("datetime").timedelta(seconds=seconds)).isoformat()


def make_log_fingerprint(log_type: str, embed) -> str:
    """Стабильный отпечаток эмбеда лога без учёта времени/цвета."""
    parts = [log_type, embed.title or ""]
    if embed.description:
        parts.append(embed.description)
    for f in embed.fields:
        parts.append(f"{f.name}\x00{f.value}")
    raw = "\x01".join(parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def try_claim_log(fingerprint: str, ttl_seconds: int = 6) -> bool:
    """Регистрирует лог как отправленный. True — первая отправка за окно."""
    now = _time.monotonic()
    prev = _claim_memory.get(fingerprint)
    if prev is not None and now - prev < ttl_seconds:
        return False
    if len(_claim_memory) > 2048:
        for k in [k for k, v in _claim_memory.items() if now - v > ttl_seconds * 10]:
            _claim_memory.pop(k, None)
    _claim_memory[fingerprint] = now

    conn = get_conn()
    cutoff = _time_ago(ttl_seconds)
    try:
        conn.execute("DELETE FROM log_sent WHERE sent_at < ?", (cutoff,))
        conn.execute(
            "INSERT INTO log_sent (fingerprint, sent_at) VALUES (?, ?)",
            (fingerprint, _utcnow()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
