# handlers/admin.py

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from database import async_session_maker
from database import crud

router = Router()

logger = logging.getLogger(__name__)


# ==============================
# FSM: Добавление врача
# ==============================

class AddDoctorFSM(StatesGroup):
    username = State()
    fio = State()


# ==============================
# Хендлеры
# ==============================

@router.message(Command("start"))
async def admin_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🛠 <b>Главное меню администратора</b>\n\n"
        "Доступные команды:\n"
        "/add_doctor — добавить нового врача"
    )


@router.message(Command("add_doctor"))
async def add_doctor_start(message: Message, state: FSMContext):
    await message.answer("Введите Telegram username врача (без @):")
    await state.set_state(AddDoctorFSM.username)


@router.message(AddDoctorFSM.username)
async def add_doctor_username(message: Message, state: FSMContext):
    raw = message.text.strip()
    username = raw.lower().replace("@", "")

    if not username:
        await message.answer("Username не может быть пустым. Введите ещё раз:")
        return

    await state.update_data(username=username)
    await message.answer("Введите ФИО врача:")
    await state.set_state(AddDoctorFSM.fio)


@router.message(AddDoctorFSM.fio)
async def add_doctor_fio(message: Message, state: FSMContext):
    fio = message.text.strip()

    if not fio:
        await message.answer("ФИО не может быть пустым. Введите ещё раз:")
        return

    data = await state.get_data()
    username = data["username"]

    async with async_session_maker() as session:
        existing_role = await crud.get_user_role(session, username)
        if existing_role:
            await message.answer(
                f"❌ Пользователь @{username} уже зарегистрирован с ролью <b>{existing_role}</b>."
            )
        else:
            await crud.add_doctor(session, username, fio)
            logger.info("Добавлен новый врач: username=%s, fio=%s", username, fio)
            await message.answer(
                f"✅ Врач <b>{fio}</b> (@{username}) успешно добавлен в систему."
            )

    await state.clear()