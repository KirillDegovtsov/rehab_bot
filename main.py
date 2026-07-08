import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from handlers import doctor_router, patient_router
from database import engine, Base


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    await init_db()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(doctor_router)
    dp.include_router(patient_router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен и готов к работе")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())