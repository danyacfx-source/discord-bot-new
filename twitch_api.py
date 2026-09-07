import asyncio
import json
import urllib.request
import urllib.error
import ssl

TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"


class TwitchStream:
    """Данные о канале и текущей трансляции."""

    def __init__(self, data: dict):
        user = data.get("data", {}).get("user") or {}
        stream = user.get("stream") or {}

        self.login = user.get("login", "")
        self.display_name = user.get("displayName", "f_a_n_e")
        self.channel_title = (user.get("broadcastSettings") or {}).get("title", "")

        self.is_live = bool(stream.get("id"))
        self.stream_title = (stream.get("title") or "").strip()
        self.viewers = stream.get("viewersCount") or 0
        self.game = (stream.get("game") or {}).get("displayName") or "Без категории"
        self.thumbnail = stream.get("previewImageURL") or ""
        self.created_at = stream.get("createdAt") or ""
        self.type = stream.get("type") or ""

    @property
    def url(self) -> str:
        return f"https://www.twitch.tv/{self.login}"


class TwitchError(Exception):
    pass


def _request(query: str) -> dict:
    """Синхронный POST-запрос к Twitch GQL."""

    payload = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        TWITCH_GQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Client-ID": TWITCH_CLIENT_ID,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise TwitchError(f"HTTP {e.code}") from e
    except Exception as e:
        raise TwitchError(str(e)) from e


_QUERY = (
    "query { user(login: \"__LOGIN__\") { id login displayName "
    "broadcastSettings { title } "
    "stream { id type viewersCount game { displayName } "
    "previewImageURL(width: 640, height: 360) title createdAt } } }"
)


def fetch_stream_sync(login: str) -> TwitchStream:
    """Получить данные о стриме канала (синхронно)."""
    query = _QUERY.replace("__LOGIN__", login)
    data = _request(query)
    return TwitchStream(data)


async def fetch_stream(login: str) -> TwitchStream:
    """Получить данные о стриме канала (асинхронная обёртка)."""
    return await asyncio.to_thread(fetch_stream_sync, login)
