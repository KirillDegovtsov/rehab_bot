import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from database import engine, Base, async_session_maker
from database.crud import bootstrap_admin
from handlers.doctor import router as doctor_router
from handlers.patient import router as patient_router
from handlers.admin import router as admin_router
from middlewares.auth import AuthMiddleware
from utils.filters import RoleFilter


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        await bootstrap_admin(session, config.ADMIN_USERNAME)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    await init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # --- Middleware: проверяет username и определяет роль для КАЖДОГО события ---
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # --- Фильтры ролей на роутеры ---
    # Фильтр вешается на роутер до его подключения к dp,
    # поэтому все хендлеры внутри роутера автоматически получают ограничение.
    admin_router.message.filter(RoleFilter("admin"))
    admin_router.callback_query.filter(RoleFilter("admin"))

    doctor_router.message.filter(RoleFilter("doctor"))
    doctor_router.callback_query.filter(RoleFilter("doctor"))

    patient_router.message.filter(RoleFilter("patient"))
    patient_router.callback_query.filter(RoleFilter("patient"))

    # --- Регистрация роутеров ---
    # Порядок важен: admin → doctor → patient
    dp.include_router(admin_router)
    dp.include_router(doctor_router)
    dp.include_router(patient_router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен и готов к работе")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())