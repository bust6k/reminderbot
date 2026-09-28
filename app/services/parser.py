from datetime import datetime, timezone

import pytz
from dateparser.search import search_dates

from app.config import settings


def parse_reminder(raw: str, user_tz: str | None = None) -> tuple[str, datetime] | None:
    tz = pytz.timezone(user_tz or settings.default_tz)
    now = datetime.now(tz)

    results = search_dates(
        raw,
        languages=["ru", "en"],
        settings={
            "RELATIVE_BASE": now,
            "TIMEZONE": str(tz),
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if not results:
        return None

    matched, when = results[0]

    text = raw.replace(matched, "").strip(" ,.-—\t\n")
    if not text:
        text = "напоминание"

    if when <= now:
        return None

    return text, when.astimezone(timezone.utc)
