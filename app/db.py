import aiosqlite
from datetime import datetime

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    remind_at  TEXT    NOT NULL,
    is_sent    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reminders_pending
    ON reminders(is_sent, remind_at);
"""


async def init_db() -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(SCHEMA)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.commit()


async def add_reminder(user_id: int, text: str, remind_at: datetime) -> int:
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute(
            "INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)",
            (user_id, text, remind_at.isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def mark_sent(reminder_id: int) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))
        await db.commit()


async def get_pending(now: datetime) -> list[tuple]:
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute(
            "SELECT id, user_id, text, remind_at FROM reminders "
            "WHERE is_sent = 0 AND remind_at > ? ORDER BY remind_at",
            (now.isoformat(),),
        )
        return await cur.fetchall()

async def is_sent(reminder_id: int) -> bool:
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute(
            "SELECT is_sent FROM reminders WHERE id = ?",
            (reminder_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return True  
        return bool(row[0])

async def claim_for_sending(reminder_id: int) -> tuple[int, str] | None: 
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute(
            "UPDATE reminders SET is_sent = 1 "
            "WHERE id = ? AND is_sent = 0 "
            "RETURNING user_id, text",
            (reminder_id,),
        )
        row = await cur.fetchone()
        await db.commit()
        if row is None:
            return None
        return row[0], row[1]


async def get_user_reminders(user_id: int, now: datetime) -> list[tuple]:
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute(
            "SELECT id, text, remind_at FROM reminders "
            "WHERE user_id = ? AND is_sent = 0 AND remind_at > ? "
            "ORDER BY remind_at",
            (user_id, now.isoformat()),
        )
        return await cur.fetchall()


async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?",
            (reminder_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0
