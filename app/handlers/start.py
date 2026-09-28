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
