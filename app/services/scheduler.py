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
