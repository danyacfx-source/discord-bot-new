import sqlite3
import threading
from datetime import datetime, timezone

DB_FILE = "wardogs.db"
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
