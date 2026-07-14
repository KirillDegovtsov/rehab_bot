from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорты клавиатур, сервисов и CRUD (тут нужно импортировать твои модули)
from keyboards.patient_kb import (patient_main_kb, disclaimer_kb, pain_scale_kb, 
                                  mobility_kb, workout_rating_kb, meal_confirm_kb)
from services.rag_service import ask_rag_assistant, recognize_meal
# from database.database import async_session_maker
# from database.crud import add_pain_log, add_workout_log

patient_router = Router()

class PatientOnboardingFSM(StatesGroup):
    waiting_name = State()
    waiting_disclaimer = State()
    waiting_pain_level = State()
    waiting_mobility = State()

class PatientMenuFSM(StatesGroup):
    main_menu = State()

class PatientMealFSM(StatesGroup):
    waiting_meal_text = State()
    waiting_confirmation = State()

class PatientWorkoutFSM(StatesGroup):
    waiting_rating = State()
    waiting_reps = State()

class PatientRAGFSM(StatesGroup):
    waiting_rag_question = State()

# --- Модуль 1 (Онбординг) ---
@patient_router.message(CommandStart())
async def cmd_start_patient(message: Message, state: FSMContext):
    # TODO: Получить данные пользователя через CRUD
    is_registered = True 
    has_pain_level = False # Проверка пройден ли онбординг
    
    if is_registered and not has_pain_level:
        await message.answer("Пожалуйста, введите ваше имя:")
        await state.set_state(PatientOnboardingFSM.waiting_name)
    else:
        await message.answer("Главное меню", reply_markup=patient_main_kb())

@patient_router.message(StateFilter(PatientOnboardingFSM.waiting_name), F.text)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Ознакомьтесь с условиями использования.", reply_markup=disclaimer_kb())
    await state.set_state(PatientOnboardingFSM.waiting_disclaimer)

@patient_router.callback_query(StateFilter(PatientOnboardingFSM.waiting_disclaimer), F.data == "disclaimer_accept")
async def process_disclaimer(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Оцените ваш уровень боли от 0 до 10:", reply_markup=pain_scale_kb())
    await state.set_state(PatientOnboardingFSM.waiting_pain_level)

@patient_router.callback_query(StateFilter(PatientOnboardingFSM.waiting_pain_level), F.data.startswith("pain_"))
async def process_pain(call: CallbackQuery, state: FSMContext):
    pain_level = int(call.data.split("_")[1])
    await state.update_data(pain_level=pain_level)
    
    # async with async_session_maker() as session:
    #     await add_pain_log(session, patient_id=call.from_user.id, pain_level=pain_level)
        
    await call.message.edit_text("Как вы передвигаетесь?", reply_markup=mobility_kb())
    await state.set_state(PatientOnboardingFSM.waiting_mobility)
    
@patient_router.callback_query(StateFilter(PatientOnboardingFSM.waiting_mobility), F.data.startswith("mob_"))
async def process_mobility(call: CallbackQuery, state: FSMContext):
    mobility = call.data.split("_")[1]
    await call.message.edit_text("Регистрация завершена! Добро пожаловать.", reply_markup=patient_main_kb())
    await state.clear()

# --- Модуль 3 и 4 (Питание и Тренировки) ---
@patient_router.message(StateFilter(PatientWorkoutFSM.waiting_rating), F.data.startswith("workout_rating_"))
async def process_workout_rating(call: CallbackQuery, state: FSMContext):
    rating = int(call.data.split("_")[2])
    await state.update_data(rating=rating)
    await call.message.edit_text("Сколько повторений вы выполнили?")
    await state.set_state(PatientWorkoutFSM.waiting_reps)

# --- Модуль 5 (RAG-ассистент) ---
@patient_router.message(F.text == "Задать вопрос ассистенту")
async def start_rag_assistant(message: Message, state: FSMContext):
    await message.answer("Задайте вопрос. Для выхода напишите 'Назад'.")
    await state.set_state(PatientRAGFSM.waiting_rag_question)

@patient_router.message(StateFilter(PatientRAGFSM.waiting_rag_question), F.text)
async def process_rag_question(message: Message, state: FSMContext):
    if message.text.lower() == "назад":
        await message.answer("Вы в главном меню.", reply_markup=patient_main_kb())
        await state.clear()
        return
        
    # TODO: Вытащить профиль из БД
    profile = {"diagnosis": "Травма колена", "mobility": "Костыли"}
    
    wait_msg = await message.answer("⏳ Анализирую базу знаний...")
    answer = await ask_rag_assistant(message.text, profile)
    await wait_msg.edit_text(answer)