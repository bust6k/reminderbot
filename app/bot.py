import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app import db
from app.config import settings
from app.handlers import reminders, start
from app.services.scheduler import restore_pending, scheduler
from dotenv import load_dotenv
from aiogram.types import BufferedInputFile
from aiogram.types.input_profile_photo_static import InputProfilePhotoStatic
import os

load_dotenv()

IMAGE_SRC = os.getenv("IMG_SRC")

async def set_bot_photo(bot,image_src: str) -> None:
    with open(image_src, "rb") as f:
        img_bytes = f.read()
    
    photo_file = BufferedInputFile(img_bytes, filename="avatar.jpg")
    
    profile_photo = InputProfilePhotoStatic(photo=photo_file)
    
    try:
        await bot.set_my_profile_photo(photo=profile_photo)
        logging.info("Аватарка бота успешно обновлена!")
    except Exception as e:
        logging.exception("Не удалось установить аватарку: %s", e)


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
    await set_bot_photo(bot,IMAGE_SRC)
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
