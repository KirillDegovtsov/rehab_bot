from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import async_session_maker, crud
from utils import format_rehab_plan_text

router = Router()


@router.message(Command("start"))
async def patient_start(message: Message, state: FSMContext):
    """
    При /start пациент регистрирует свой chat_id в БД по username.
    Если план уже одобрен — сразу отправляем его.
    Если нет — сообщаем что план ещё не готов.
    """
    username = message.from_user.username

    if not username:
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "⚠️ У вас не установлен username в Telegram. "
            "Попросите вашего врача уточнить как вас найти в системе."
        )
        return

    async with async_session_maker() as session:
        patient = await crud.get_patient_by_username(session, username)

        if not patient:
            await message.answer(
                "👋 Добро пожаловать!\n\n"
                "Вы пока не зарегистрированы в системе реабилитации. "
                "Обратитесь к вашему лечащему врачу — "
                "он добавит вас в систему."
            )
            return

        # Сохраняем chat_id чтобы врач мог отправлять уведомления
        if patient.chat_id != message.from_user.id:
            await crud.update_patient(
                session,
                patient.id,
                {"chat_id": message.from_user.id}
            )

        # Проверяем наличие активного плана
        plan = await crud.get_rehab_plan(session, patient.id)

        if plan and plan.status == "active":
            formatted_text = format_rehab_plan_text(
                plan.exercises_json,
                plan.nutrition_json
            )
            await message.answer(
                f"👋 Добро пожаловать, {patient.name}!\n\n"
                f"✅ Ваш план реабилитации уже готов:\n\n"
                f"{formatted_text}",
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                f"👋 Добро пожаловать, {patient.name}!\n\n"
                "⏳ Ваш лечащий врач ещё не составил план реабилитации. "
                "Как только план будет готов и утверждён — "
                "вы получите уведомление прямо здесь."
            )


@router.message()
async def patient_unknown_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    await message.answer(
        "⚠️ Неизвестная команда. "
        "Если у вас есть вопросы — обратитесь к вашему лечащему врачу."
    )