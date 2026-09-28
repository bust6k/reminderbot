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
