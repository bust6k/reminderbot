from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я бот-напоминалка.\n\n"
        "Напиши в свободной форме:\n"
        "<code>напомни через 30 минут позвонить маме</code>\n"
        "<code>завтра в 15:00 встреча с командой</code>\n\n"
        "<b>Команды:</b>\n"
        "/remind &lt;текст&gt; — добавить напоминание\n"
        "/list — активные напоминания\n"
        "/cancel &lt;id&gt; — отменить напоминание\n"
    )
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app import db
from app.services.parser import parse_reminder
from app.services.scheduler import cancel, schedule

router = Router()

TRIGGER_WORDS = ("напомни", "напоминание", "remind", "через ", "завтра", "послезавтра")
TRIGGER_PREFIXES = ("напомни мне", "напомни", "remind me", "remind")


async def _create(message: Message, bot: Bot, raw: str) -> None:
    parsed = parse_reminder(raw)
    if parsed is None:
        await message.answer(
            "Не понял время 🤔\n"
            "Попробуй так: <code>через 20 минут выпить воды</code>\n"
            "Или так: <code>завтра в 9:30 зарядка</code>"
        )
        return

    text, when_utc = parsed
    reminder_id = await db.add_reminder(message.from_user.id, text, when_utc)
    await schedule(bot, reminder_id, when_utc)

    local = when_utc.astimezone()
    await message.answer(
        f"✅ Запомнил #{reminder_id}: <b>{text}</b>\n"
        f"⏰ {local.strftime('%d.%m.%Y %H:%M')}"
    )


@router.message(Command("remind"))
async def cmd_remind(message: Message, bot: Bot) -> None:
    args = (message.text or "").partition(" ")[2].strip()
    if not args:
        await message.answer("Формат: <code>/remind через час позвонить маме</code>")
        return
    await _create(message, bot, args)


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    now = datetime.now(timezone.utc)
    rows = await db.get_user_reminders(message.from_user.id, now)
    if not rows:
        await message.answer("Активных напоминаний нет.")
        return

    lines = ["<b>Активные напоминания:</b>"]
    for reminder_id, text, remind_at_str in rows:
        when = datetime.fromisoformat(remind_at_str).astimezone()
        lines.append(f"#{reminder_id} — {when.strftime('%d.%m %H:%M')} — {text}")
    await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    args = (message.text or "").partition(" ")[2].strip()
    if not args.isdigit():
        await message.answer("Формат: <code>/cancel 42</code>")
        return

    reminder_id = int(args)
    ok = await db.delete_reminder(reminder_id, message.from_user.id)
    if not ok:
        await message.answer(f"#{reminder_id} не найден или не твой.")
        return

    await cancel(reminder_id)
    await message.answer(f"🗑 Отменил #{reminder_id}")


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot) -> None:
    text = (message.text or "").strip()
    lower = text.lower()

    if not any(w in lower for w in TRIGGER_WORDS):
        return

    cleaned = text
    for prefix in TRIGGER_PREFIXES:
        idx = lower.find(prefix)
        if idx != -1:
            cleaned = (text[:idx] + text[idx + len(prefix):]).strip(" ,.-—")
            break

    if not cleaned:
        return

    await _create(message, bot, cleaned)
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
import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import db

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _fire(bot: Bot, reminder_id: int) -> None:
    claimed = await db.claim_for_sending(reminder_id)
    if claimed is None:
        log.debug("reminder=%s already sent or missing", reminder_id)
        return

    user_id, text = claimed
    try:
        await bot.send_message(user_id, f"⏰ <b>Напоминание:</b>\n{text}")
        log.info("sent reminder=%s user=%s", reminder_id, user_id)
    except Exception as e:  # noqa: BLE001
        log.warning("send failed reminder=%s user=%s: %s", reminder_id, user_id, e)


async def schedule(bot: Bot, reminder_id: int, remind_at: datetime) -> None:
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)

    scheduler.add_job(
        _fire,
        "date",
        run_date=remind_at,
        args=[bot, reminder_id],
        id=f"reminder:{reminder_id}",
        replace_existing=True,
        misfire_grace_time=3600,
    )


async def cancel(reminder_id: int) -> None:
    job = scheduler.get_job(f"reminder:{reminder_id}")
    if job is not None:
        job.remove()


async def restore_pending(bot: Bot) -> None:
    now = datetime.now(timezone.utc)

    pending = await db.get_pending(datetime.min.replace(tzinfo=timezone.utc))

    future = overdue = 0
    for row in pending:
        reminder_id, _user_id, _text, remind_at_str = row
        remind_at = datetime.fromisoformat(remind_at_str)
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=timezone.utc)

        if remind_at <= now:
            overdue += 1
            await _fire(bot, reminder_id)
        else:
            future += 1
            await schedule(bot, reminder_id, remind_at)

    log.info("restore done: future=%d overdue=%d", future, overdue)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    db_path: str = "./reminders.db"
    default_tz: str = "Europe/Moscow"


settings = Settings()
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app import db
from app.config import settings
from app.handlers import reminders, start
from app.services.scheduler import restore_pending, scheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    await db.init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(reminders.router)

    await restore_pending(bot)
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
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
