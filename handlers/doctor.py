import re
import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from database import async_session_maker, crud
from services import gigachat_client
from keyboards.doctor_kb import (
    main_menu_kb,
    back_kb,
    gender_kb,
    patient_list_kb,
    patient_card_kb,
    edit_patient_fields_kb,
    get_edit_plan_kb,
    exercises_list_kb,
    exercise_edit_kb,
    nutrition_menu_kb,
    confirm_generation_kb,
    meal_actions_kb,
    view_plan_kb,
)
from utils import format_rehab_plan_text

import copy
from sqlalchemy.orm.attributes import flag_modified

router = Router()


# ===========================================================================
# FSM КЛАССЫ
# ===========================================================================

class PatientRegistrationFSM(StatesGroup):
    username           = State()
    name               = State()
    gender             = State()
    age                = State()
    diagnosis          = State()
    surgery_date       = State()
    fracture_type      = State()
    surgery_method     = State()
    comorbidities      = State()
    health_status      = State()
    confirm_generation = State()


class EditPlanFSM(StatesGroup):
    waiting_for_sets  = State()
    waiting_for_reps  = State()
    waiting_for_meal  = State()
    add_exercise_name = State()
    add_exercise_desc = State()
    add_exercise_sets = State()
    add_exercise_reps = State()
    add_meal_name     = State()
    add_meal_food     = State()


class EditPatientFieldFSM(StatesGroup):
    waiting_value = State()


# ===========================================================================
# СЛОВАРЬ НАВИГАЦИИ ПО ШАГАМ FSM (для кнопки Назад)
# ===========================================================================

FSM_STEPS = {
    PatientRegistrationFSM.username: (
        None, "Регистрация отменена.", None
    ),
    PatientRegistrationFSM.name: (
        PatientRegistrationFSM.username,
        "Введите Telegram Username пациента (например, @ivan_ivanov):",
        back_kb()
    ),
    PatientRegistrationFSM.gender: (
        PatientRegistrationFSM.name,
        "Введите ФИО пациента (отчество указывается при наличии):",
        back_kb()
    ),
    PatientRegistrationFSM.age: (
        PatientRegistrationFSM.gender,
        "Укажите пол пациента:",
        back_kb()
    ),
    PatientRegistrationFSM.diagnosis: (
        PatientRegistrationFSM.age,
        "Введите возраст пациента (числом):",
        back_kb()
    ),
    PatientRegistrationFSM.surgery_date: (
        PatientRegistrationFSM.diagnosis,
        "Введите диагноз пациента:",
        back_kb()
    ),
    PatientRegistrationFSM.fracture_type: (
        PatientRegistrationFSM.surgery_date,
        "Введите дату операции (например, ДД.ММ.ГГГГ):",
        back_kb()
    ),
    PatientRegistrationFSM.surgery_method: (
        PatientRegistrationFSM.fracture_type,
        "Введите тип перелома (или 'Нет'):",
        back_kb()
    ),
    PatientRegistrationFSM.comorbidities: (
        PatientRegistrationFSM.surgery_method,
        "Укажите метод операции:",
        back_kb()
    ),
    PatientRegistrationFSM.health_status: (
        PatientRegistrationFSM.comorbidities,
        "Укажите сопутствующие заболевания (или 'Нет'):",
        back_kb()
    ),
    PatientRegistrationFSM.confirm_generation: (
        PatientRegistrationFSM.health_status,
        "Опишите текущее общее состояние здоровья пациента:",
        back_kb()
    ),
}

MEAL_NAMES_RU = {
    "breakfast": "Завтрак",
    "lunch":     "Обед",
    "dinner":    "Ужин",
}
    
PATIENT_FIELD_MAP = {
    "epat_name":         ("name",           "ФИО"),
    "epat_age":          ("age",            "возраст (числом)"),
    "epat_diagnosis":    ("diagnosis",      "диагноз"),
    "epat_surgery_date": ("surgery_date",   "дату операции (ДД.ММ.ГГГГ)"),
    "epat_fracture":     ("fracture_type",  "тип перелома"),
    "epat_method":       ("surgery_method", "метод операции"),
    "epat_comorbid":     ("comorbidities",  "сопутствующие заболевания"),
    "epat_health":       ("health_status",  "состояние здоровья"),
    # ИЗМЕНЕНО: текст подсказки обновлён — @ теперь обязателен
    "epat_username":     ("username",       "Telegram username (с @, например @ivan_ivanov)"),
}

# ===========================================================================
# ВАЛИДАТОРЫ
# ===========================================================================

def validate_username(text: str) -> tuple[bool, str]:
    """Валидация Telegram username. Символ @ обязателен."""
    stripped = text.strip()
    if not stripped.startswith("@"):
        return (
            False,
            "❌ Username должен начинаться с символа @.\n"
            "Введите username в формате @username. Повторите ввод:"
        )
    cleaned = stripped.lstrip("@")
    if not re.match(r'^[a-zA-Z0-9_]{3,32}$', cleaned):
        return (
            False,
            "❌ Некорректный username. После @ должны идти только "
            "латинские буквы, цифры и _, длиной от 3 до 32 символов. "
            "Повторите ввод:"
        )
    return (True, cleaned)


def validate_age(text: str) -> tuple[bool, str | int]:
    """Валидация возраста пациента."""
    if not text.strip().isdigit():
        return (
            False,
            "❌ Возраст должен быть положительным числом от 1 до 120. "
            "Повторите ввод:"
        )
    age = int(text.strip())
    if age < 1 or age > 120:
        return (
            False,
            "❌ Возраст должен быть положительным числом от 1 до 120. "
            "Повторите ввод:"
        )
    return (True, age)


def validate_fio(text: str) -> tuple[bool, str]:
    """Валидация ФИО пациента."""
    words = text.strip().split()
    if len(words) < 2 or len(words) > 3:
        return (
            False,
            "❌ Введите корректное ФИО: 2 слова (Фамилия Имя) или 3 слова "
            "(Фамилия Имя Отчество). Используйте только кириллицу. "
            "Повторите ввод:"
        )
    for word in words:
        if not re.match(r'^[А-ЯЁа-яё\-]+$', word):
            return (
                False,
                "❌ Введите корректное ФИО: 2 слова (Фамилия Имя) или 3 слова "
                "(Фамилия Имя Отчество). Используйте только кириллицу. "
                "Повторите ввод:"
            )
    return (True, text.strip())


def validate_surgery_date(text: str) -> tuple[bool, str]:
    """Валидация даты операции."""
    text = text.strip()
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
        return (
            False,
            "❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ "
            "(например, 15.03.2024):"
        )
    day, month, year = int(text[:2]), int(text[3:5]), int(text[6:])
    if day < 1 or day > 31:
        return (False, "❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ (например, 15.03.2024):")
    if month < 1 or month > 12:
        return (False, "❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ (например, 15.03.2024):")
    if year < 1900:
        return (False, "❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ (например, 15.03.2024):")
    try:
        parsed_date = datetime.date(year, month, day)
    except ValueError:
        return (False, "❌ Такой даты не существует. Проверьте день и месяц. Повторите ввод:")
    if parsed_date > datetime.date.today():
        return (False, "❌ Дата операции не может быть в будущем. Повторите ввод:")
    return (True, text)

def _format_field(value) -> str:
    if value is None or str(value).strip() == "":
        return "Не указано"
    return str(value)


def _build_patient_card_text(patient) -> str:
    gender_ru = {"male": "Мужской", "female": "Женский"}.get(
        patient.gender, _format_field(patient.gender)
    )
    return (
        f"👤 *Карточка пациента*\n\n"
        f"*ФИО:* {_format_field(patient.name)}\n"
        f"*Пол:* {gender_ru}\n"
        f"*Возраст:* {_format_field(patient.age)}\n"
        f"*Диагноз:* {_format_field(patient.diagnosis)}\n"
        f"*Дата операции:* {_format_field(patient.surgery_date)}\n"
        f"*Тип перелома:* {_format_field(patient.fracture_type)}\n"
        f"*Метод операции:* {_format_field(patient.surgery_method)}\n"
        f"*Сопут. заболевания:* {_format_field(patient.comorbidities)}\n"
        f"*Состояние здоровья:* {_format_field(patient.health_status)}\n"
        f"*Username:* @{_format_field(patient.username)}"
    )


async def _show_patient_card_by_id(message: Message, patient_id: int):
    async with async_session_maker() as session:
        patient = await crud.get_patient(session, patient_id)
        if not patient:
            await message.answer("Пациент не найден.")
            await _send_main_menu(message)
            return
        text = _build_patient_card_text(patient)
        await message.answer(
            text,
            reply_markup=patient_card_kb(patient.id),
            parse_mode="Markdown"
        )


async def _send_main_menu(message: Message):
    await message.answer("🏠 Главное меню", reply_markup=main_menu_kb())


@router.message(F.text == "🔙 Назад")
async def step_back(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == EditPatientFieldFSM.waiting_value.state:
        data = await state.get_data()
        patient_id = data.get("patient_id")
        await state.clear()
        if patient_id:
            await message.answer(
                "Выберите поле для редактирования:",
                reply_markup=ReplyKeyboardRemove()
            )
            await message.answer(
                "👇 Выберите поле:",
                reply_markup=edit_patient_fields_kb(patient_id)
            )
        else:
            await message.answer(
                "Редактирование отменено.",
                reply_markup=ReplyKeyboardRemove()
            )
            await _send_main_menu(message)
        return

    if current_state == EditPlanFSM.add_meal_name.state:
        data = await state.get_data()
        patient_id = data.get("patient_id")
        await state.clear()
        async with async_session_maker() as session:
            plan = await crud.get_rehab_plan(session, patient_id)
            meals = plan.nutrition_json.get("nutrition", {}).get("meals", {}) if plan else None
        await message.answer("Добавление приёма пищи отменено.", reply_markup=ReplyKeyboardRemove())
        await message.answer(
            "Выберите приём пищи для редактирования:",
            reply_markup=nutrition_menu_kb(patient_id, meals)
        )
        return

    if current_state == EditPlanFSM.add_meal_food.state:
        await state.set_state(EditPlanFSM.add_meal_name)
        await message.answer(
            "Введите название приёма пищи (только на русском):",
            reply_markup=back_kb()
        )
        return

    if current_state == EditPlanFSM.waiting_for_meal.state:
        data = await state.get_data()
        patient_id = data.get("patient_id")
        meal_key = data.get("meal_key")
        await state.clear()
        await message.answer(
            "Редактирование отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        if patient_id and meal_key:
            meal_name = MEAL_NAMES_RU.get(meal_key, meal_key.capitalize())
            await message.answer(
                f"Приём пищи: *{meal_name}*\nВыберите действие:",
                reply_markup=meal_actions_kb(meal_key, patient_id),
                parse_mode="Markdown"
            )
        else:
            await _send_main_menu(message)
        return

    if current_state in (
        EditPlanFSM.waiting_for_sets.state,
        EditPlanFSM.waiting_for_reps.state,
    ):
        await state.clear()
        await message.answer(
            "Редактирование отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        await _send_main_menu(message)
        return

    if current_state == EditPlanFSM.add_exercise_name.state:
        data = await state.get_data()
        patient_id = data.get("patient_id")
        await state.clear()
        async with async_session_maker() as session:
            plan = await crud.get_rehab_plan(session, patient_id)
        exercises = plan.exercises_json.get("exercises", []) if plan else []
        await message.answer("↩️", reply_markup=ReplyKeyboardRemove())
        await message.answer(
            "Выберите упражнение для редактирования:",
            reply_markup=exercises_list_kb(patient_id, exercises)
        )
        return

    if current_state == EditPlanFSM.add_exercise_desc.state:
        await state.set_state(EditPlanFSM.add_exercise_name)
        await message.answer(
            "Введите название нового упражнения:",
            reply_markup=back_kb()
        )
        return

    if current_state == EditPlanFSM.add_exercise_sets.state:
        await state.set_state(EditPlanFSM.add_exercise_desc)
        await message.answer(
            "Введите описание упражнения (как выполнять):",
            reply_markup=back_kb()
        )
        return

    if current_state == EditPlanFSM.add_exercise_reps.state:
        await state.set_state(EditPlanFSM.add_exercise_sets)
        await message.answer(
            "Введите количество подходов (целое число больше 0):",
            reply_markup=back_kb()
        )
        return

    for state_obj, (prev_state, text, kb) in FSM_STEPS.items():
        if current_state == state_obj.state:
            if prev_state is None:
                await state.clear()
                await message.answer(text, reply_markup=ReplyKeyboardRemove())
                await _send_main_menu(message)
            else:
                await state.set_state(prev_state)
                if prev_state == PatientRegistrationFSM.gender:
                    await message.answer(text, reply_markup=back_kb())
                    await message.answer("👇 Выберите пол:", reply_markup=gender_kb())
                else:
                    await message.answer(text, reply_markup=kb)
            return

    await message.answer(
        "Нет предыдущего шага.",
        reply_markup=ReplyKeyboardRemove()
    )
    await _send_main_menu(message)
    
def validate_russian_text(text: str) -> tuple[bool, str]:
    stripped = text.strip()
    if not stripped:
        return (False, "❌ Текст не может быть пустым. Повторите ввод:")
    if re.search(r'[a-zA-Z]', stripped):
        return (False, "❌ Текст должен быть написан на русском языке. Латинские буквы недопустимы. Повторите ввод:")
    if not re.search(r'[а-яёА-ЯЁ]', stripped):
        return (False, "❌ Текст должен содержать хотя бы одно слово на русском языке. Повторите ввод:")
    return (True, stripped)

# ===========================================================================
# ГЛАВНОЕ МЕНЮ
# ===========================================================================

@router.message(Command("start"))
async def cmd_start_doctor(message: Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        await crud.get_or_create_doctor(
            session, message.from_user.id, message.from_user.full_name
        )
    await message.answer(
        "👨‍⚕️ Добро пожаловать в панель лечащего врача.",
        reply_markup=ReplyKeyboardRemove()
    )
    await _send_main_menu(message)


@router.callback_query(F.data == "menu_add_patient")
async def cb_add_patient(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer(
        "Введите Telegram Username пациента в формате @username:",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.username)
    await call.answer()


@router.callback_query(F.data == "menu_patients_list")
async def cb_patients_list(call: CallbackQuery):
    async with async_session_maker() as session:
        doctor = await crud.get_or_create_doctor(
            session, call.from_user.id, call.from_user.full_name
        )
        patients = await crud.get_patients_by_doctor(session, doctor.id)

    if not patients:
        await call.message.edit_text(
            "Список пациентов пуст.",
            reply_markup=main_menu_kb()
        )
        await call.answer()
        return

    await call.message.edit_text(
        "Ваши пациенты:",
        reply_markup=patient_list_kb(patients)
    )
    await call.answer()


@router.callback_query(F.data == "menu_back")
async def cb_menu_back(call: CallbackQuery):
    await call.message.edit_text("🏠 Главное меню", reply_markup=main_menu_kb())
    await call.answer()


# --- CRUD: РЕГИСТРАЦИЯ ПАЦИЕНТА (ВЕСЬ ЦИКЛ) ---
@router.message(PatientRegistrationFSM.username)
async def process_username(message: Message, state: FSMContext):
    valid, result = validate_username(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return

    async with async_session_maker() as session:
        existing = await crud.get_patient_by_username(session, result)
    if existing:
        await message.answer(
            f"❌ Пациент с username @{result} уже зарегистрирован в системе. "
            f"Введите другой username:",
            reply_markup=back_kb()
        )
        return

    await state.update_data(username=result)
    await message.answer(
        "Введите ФИО пациента (отчество указывается при наличии):",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.name)


@router.message(PatientRegistrationFSM.name)
async def process_name(message: Message, state: FSMContext):
    valid, result = validate_fio(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(name=result)
    await message.answer(
        "Укажите пол пациента:",
        reply_markup=back_kb()
    )
    await message.answer("👇 Выберите пол:", reply_markup=gender_kb())
    await state.set_state(PatientRegistrationFSM.gender)


@router.callback_query(
    F.data.in_({"gender_male", "gender_female"}),
    PatientRegistrationFSM.gender
)
async def process_gender(call: CallbackQuery, state: FSMContext):
    gender = "male" if call.data == "gender_male" else "female"
    await state.update_data(gender=gender)
    await call.message.answer(
        "✅ Пол выбран. Введите возраст пациента (числом):",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.age)
    await call.answer()
    
@router.message(PatientRegistrationFSM.gender)
async def process_gender_invalid(message: Message):
    await message.answer(
        "⚠️ Пожалуйста, выберите пол с помощью кнопок ниже:",
        reply_markup=gender_kb()
    )


@router.message(PatientRegistrationFSM.age)
async def process_age(message: Message, state: FSMContext):
    valid, result = validate_age(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(age=result)
    await message.answer("Введите диагноз пациента:", reply_markup=back_kb())
    await state.set_state(PatientRegistrationFSM.diagnosis)


@router.message(PatientRegistrationFSM.diagnosis)
async def process_diagnosis(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(diagnosis=result)
    await message.answer(
        "Введите дату операции (например, ДД.ММ.ГГГГ):",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.surgery_date)


@router.message(PatientRegistrationFSM.surgery_date)
async def process_surgery_date(message: Message, state: FSMContext):
    valid, result = validate_surgery_date(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(surgery_date=result)
    await message.answer(
        "Введите тип перелома (или напишите 'Нет'):",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.fracture_type)


@router.message(PatientRegistrationFSM.fracture_type)
async def process_fracture_type(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() != "нет":
        valid, result = validate_russian_text(text)
        if not valid:
            await message.answer(result, reply_markup=back_kb())
            return
        text = result
    await state.update_data(fracture_type=text)
    await message.answer("Укажите метод операции:", reply_markup=back_kb())
    await state.set_state(PatientRegistrationFSM.surgery_method)


@router.message(PatientRegistrationFSM.surgery_method)
async def process_surgery_method(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(surgery_method=result)
    await message.answer(
        "Укажите сопутствующие заболевания (или напишите 'Нет'):",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.comorbidities)


@router.message(PatientRegistrationFSM.comorbidities)
async def process_comorbidities(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() != "нет":
        valid, result = validate_russian_text(text)
        if not valid:
            await message.answer(result, reply_markup=back_kb())
            return
        text = result
    await state.update_data(comorbidities=text)
    await message.answer(
        "Опишите текущее общее состояние здоровья пациента:",
        reply_markup=back_kb()
    )
    await state.set_state(PatientRegistrationFSM.health_status)


@router.message(PatientRegistrationFSM.health_status)
async def process_health_status(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(health_status=result)
    data = await state.get_data()
    await state.set_state(PatientRegistrationFSM.confirm_generation)

    summary = (
        f"📋 *Проверьте данные пациента:*\n\n"
        f"*Username:* @{data.get('username')}\n"
        f"*ФИО:* {data.get('name')}\n"
        f"*Пол:* {'Мужской' if data.get('gender') == 'male' else 'Женский'}\n"
        f"*Возраст:* {data.get('age')}\n"
        f"*Диагноз:* {data.get('diagnosis')}\n"
        f"*Дата операции:* {data.get('surgery_date')}\n"
        f"*Тип перелома:* {data.get('fracture_type')}\n"
        f"*Метод операции:* {data.get('surgery_method')}\n"
        f"*Сопут. заболевания:* {data.get('comorbidities')}\n"
        f"*Состояние здоровья:* {data.get('health_status')}\n\n"
        f"Всё верно? Нажмите кнопку ниже для генерации или *🔙 Назад* для исправления."
    )
    await message.answer(summary, reply_markup=back_kb(), parse_mode="Markdown")
    await message.answer("👇 Подтвердите:", reply_markup=confirm_generation_kb())
    
@router.callback_query(F.data == "confirm_generate_plan")
async def cb_confirm_generate_plan(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    msg = await call.message.answer(
        "⏳ Данные собраны. Сохраняю и генерирую план через GigaChat...",
        reply_markup=ReplyKeyboardRemove()
    )
    await call.answer()

    async with async_session_maker() as session:
        doctor = await crud.get_or_create_doctor(
            session, call.from_user.id, call.from_user.full_name
        )
        patient = await crud.create_patient(session, doctor.id, data)
        try:
            draft = await gigachat_client.generate_draft_plan(data)
            plan_data = {
                "exercises_json": {"exercises": draft.get("exercises", [])},
                "nutrition_json": {"nutrition": draft.get("nutrition", {})}
            }
            plan = await crud.create_or_update_rehab_plan(session, patient.id, plan_data)
            formatted_text = format_rehab_plan_text(plan.exercises_json, plan.nutrition_json)
            text = f"📋 *Черновик плана для {patient.name}*\n\n{formatted_text}"
            await msg.delete()
            await call.message.answer(
                text,
                reply_markup=get_edit_plan_kb(patient.id, status="draft", show_back_button=False),
                parse_mode="Markdown"
            )
        except Exception as e:
            await msg.delete()
            await call.message.answer(f"❌ Ошибка генерации: {str(e)}")
            await _send_main_menu(call.message)
  
            
@router.message(PatientRegistrationFSM.confirm_generation)
async def confirm_generation_invalid_input(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ Пожалуйста, воспользуйтесь кнопками ниже.",
        reply_markup=back_kb()
    )
    await message.answer(
        "Нажмите кнопку, чтобы сгенерировать реабилитационный план:",
        reply_markup=confirm_generation_kb()
    )


# ===========================================================================
# СПИСОК ПАЦИЕНТОВ
# ===========================================================================

@router.callback_query(F.data == "back_to_list")
async def cb_back_to_list(call: CallbackQuery):
    async with async_session_maker() as session:
        doctor = await crud.get_or_create_doctor(
            session, call.from_user.id, call.from_user.full_name
        )
        patients = await crud.get_patients_by_doctor(session, doctor.id)

    if not patients:
        await call.message.edit_text(
            "Список пациентов пуст.",
            reply_markup=main_menu_kb()
        )
        await call.answer()
        return

    await call.message.edit_text(
        "Ваши пациенты:",
        reply_markup=patient_list_kb(patients)
    )
    await call.answer()


# ===========================================================================
# КАРТОЧКА ПАЦИЕНТА
# ===========================================================================

@router.callback_query(F.data.startswith("patient_card_"))
async def show_patient_card(call: CallbackQuery):
    patient_id = int(call.data.split("_")[2])
    async with async_session_maker() as session:
        patient = await crud.get_patient(session, patient_id)
        if not patient:
            await call.answer("Пациент не найден.", show_alert=True)
            return
        text = _build_patient_card_text(patient)
        await call.message.edit_text(
            text,
            reply_markup=patient_card_kb(patient.id),
            parse_mode="Markdown"
        )
    await call.answer()


@router.callback_query(F.data.startswith("delete_pat_"))
async def delete_patient_handler(call: CallbackQuery):
    patient_id = int(call.data.split("_")[2])
    async with async_session_maker() as session:
        # Читаем doctor_id ДО удаления, пока пациент ещё есть в БД
        patient = await crud.get_patient(session, patient_id)
        doctor_id = patient.doctor_id if patient else None

        await crud.delete_patient(session, patient_id)

        # Получаем обновлённый список пациентов этого врача
        patients = await crud.get_patients_by_doctor(session, doctor_id) if doctor_id else []

    if patients:
        await call.message.edit_text(
            "✅ Пациент и его план успешно удалены.\n\nВыберите пациента из списка ниже:",
            reply_markup=patient_list_kb(patients)
        )
    else:
        await call.message.edit_text(
            "✅ Пациент и его план успешно удалены. Список пациентов пуст.",
            reply_markup=main_menu_kb()
        )
    await call.answer()

# ===========================================================================
# РЕДАКТИРОВАНИЕ ДАННЫХ ПАЦИЕНТА
# ===========================================================================

@router.callback_query(F.data.startswith("edit_pat_"))
async def edit_patient_start(call: CallbackQuery, state: FSMContext):
    patient_id = int(call.data.split("_")[2])
    await state.update_data(patient_id=patient_id)
    await call.message.edit_text(
        "Выберите поле для редактирования:",
        reply_markup=edit_patient_fields_kb(patient_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("epat_cancel_"))
async def edit_patient_cancel(call: CallbackQuery, state: FSMContext):
    patient_id = int(call.data.split("_")[2])
    await state.clear()
    async with async_session_maker() as session:
        patient = await crud.get_patient(session, patient_id)
        if not patient:
            await call.answer("Пациент не найден.", show_alert=True)
            return
        text = _build_patient_card_text(patient)
        await call.message.edit_text(
            text,
            reply_markup=patient_card_kb(patient.id),
            parse_mode="Markdown"
        )
    await call.answer()


@router.callback_query(F.data.startswith("epat_gender_"))
async def edit_patient_gender_start(call: CallbackQuery, state: FSMContext):
    patient_id = int(call.data.split("_")[2])
    await state.update_data(patient_id=patient_id, db_field="gender", field_ru="пол")
    await state.set_state(EditPatientFieldFSM.waiting_value)
    await call.message.edit_text(
        "Выберите новый пол пациента:",
        reply_markup=gender_kb()
    )
    await call.answer()


@router.callback_query(
    F.data.in_({"gender_male", "gender_female"}),
    EditPatientFieldFSM.waiting_value
)
async def edit_patient_gender_save(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    patient_id = data.get("patient_id")
    gender = "male" if call.data == "gender_male" else "female"

    async with async_session_maker() as session:
        await crud.update_patient(session, patient_id, {"gender": gender})

    await state.set_state(None)
    await call.message.edit_text(
        "✅ Пол успешно обновлён!\n\nВыберите следующее поле или нажмите Отмена:",
        reply_markup=edit_patient_fields_kb(patient_id)
    )
    await call.answer()


@router.callback_query(
    lambda c: any(c.data.startswith(k + "_") for k in PATIENT_FIELD_MAP)
)
async def edit_patient_field_start(call: CallbackQuery, state: FSMContext):
    matched_key = next(k for k in PATIENT_FIELD_MAP if call.data.startswith(k + "_"))
    patient_id = int(call.data[len(matched_key) + 1:])
    db_field, field_ru = PATIENT_FIELD_MAP[matched_key]

    await state.update_data(patient_id=patient_id, db_field=db_field, field_ru=field_ru)
    await state.set_state(EditPatientFieldFSM.waiting_value)

    await call.message.answer(
        f"Введите новое значение для поля *{field_ru}*:",
        reply_markup=back_kb(),
        parse_mode="Markdown"
    )
    await call.answer()


@router.message(EditPatientFieldFSM.waiting_value)
async def edit_patient_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    patient_id = data["patient_id"]
    db_field = data["db_field"]
    field_ru = data["field_ru"]
    new_value = message.text

    # Применяем валидатор в зависимости от поля
    if db_field == "name":
        valid, result = validate_fio(new_value)
        if not valid:
            await message.answer(result, reply_markup=back_kb())
            return
        new_value = result

    elif db_field == "age":
        valid, result = validate_age(new_value)
        if not valid:
            await message.answer(result, reply_markup=back_kb())
            return
        new_value = result

    elif db_field == "surgery_date":
        valid, result = validate_surgery_date(new_value)
        if not valid:
            await message.answer(result, reply_markup=back_kb())
            return
        new_value = result

    elif db_field == "username":
        valid, result = validate_username(new_value)
        if not valid:
            await message.answer(result, reply_markup=back_kb())
            return
        new_value = result

    async with async_session_maker() as session:
        await crud.update_patient(session, patient_id, {db_field: new_value})

    await state.set_state(None)
    await message.answer(
        f"✅ Поле *{field_ru}* успешно обновлено!\n\n"
        f"Выберите следующее поле для редактирования или нажмите Отмена:",
        reply_markup=edit_patient_fields_kb(patient_id),
        parse_mode="Markdown"
    )


# ===========================================================================
# РЕДАКТИРОВАНИЕ ПЛАНА РЕАБИЛИТАЦИИ
# ===========================================================================

@router.callback_query(F.data.startswith("view_plan_"))
async def view_and_edit_plan(call: CallbackQuery):
    patient_id = int(call.data.split("_")[2])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await call.answer("План ещё не создан!", show_alert=True)
            return
        formatted_text = format_rehab_plan_text(plan.exercises_json, plan.nutrition_json)
        status_ru = "✅ Активен" if plan.status == "active" else "📝 Черновик"
        text = f"📋 *План реабилитации*\nСтатус: {status_ru}\n\n{formatted_text}"
        await call.message.edit_text(
            text,
            reply_markup=view_plan_kb(patient_id),
            parse_mode="Markdown"
        )
    await call.answer()
    
    
@router.callback_query(F.data.startswith("open_edit_plan_"))
async def cb_open_edit_plan(call: CallbackQuery):
    patient_id = int(call.data.split("open_edit_plan_")[1])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await call.answer("План не найден.", show_alert=True)
            return
        formatted_text = format_rehab_plan_text(plan.exercises_json, plan.nutrition_json)
        status_ru = "✅ Активен" if plan.status == "active" else "📝 Черновик"
        text = f"📋 *План реабилитации*\nСтатус: {status_ru}\n\n{formatted_text}"
        await call.message.edit_text(
            text,
            reply_markup=get_edit_plan_kb(patient_id, status=plan.status, show_back_button=True),
            parse_mode="Markdown"
        )
    await call.answer()


# --- РЕДАКТИРОВАНИЕ ПЛАНА (УПРАЖНЕНИЯ, ПОДХОДЫ И Т.Д.) ---
# --- МЕНЮ ВЫБОРА УПРАЖНЕНИЯ ---
@router.callback_query(F.data.startswith("edit_exercises_menu_"))
async def cb_edit_exercises_menu(call: CallbackQuery):
    patient_id = int(call.data.split("edit_exercises_menu_")[1])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
    if not plan:
        await call.answer("План не найден.", show_alert=True)
        return
    exercises = plan.exercises_json.get("exercises", [])
    await call.message.edit_text(
        "Выберите упражнение для редактирования:",
        reply_markup=exercises_list_kb(patient_id, exercises)
    )
    await call.answer()


# --- ВЫБОР КОНКРЕТНОГО УПРАЖНЕНИЯ ---
@router.callback_query(F.data.startswith("select_exercise_"))
async def cb_select_exercise(call: CallbackQuery):
    parts = call.data.split("_")
    # формат: select_exercise_{patient_id}_{index}
    exercise_index = int(parts[-1])
    patient_id = int(parts[-2])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
    if not plan:
        await call.answer("План не найден.", show_alert=True)
        return
    try:
        exercise = plan.exercises_json["exercises"][exercise_index]
    except IndexError:
        await call.answer("❌ Упражнение не найдено.", show_alert=True)
        return
    text = (
        f"🏋️ *{exercise['name']}*\n"
        f"Подходы: {exercise.get('sets', '—')} | Повторения: {exercise.get('reps', '—')}\n\n"
        f"Что хотите изменить?"
    )
    await call.message.edit_text(
        text,
        reply_markup=exercise_edit_kb(patient_id, exercise_index),
        parse_mode="Markdown"
    )
    await call.answer()


# --- ЗАПРОС НОВОГО ЗНАЧЕНИЯ ПОДХОДОВ ---
@router.callback_query(F.data.startswith("edit_sets_"))
async def cb_edit_sets(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    # формат: edit_sets_{patient_id}_{exercise_index}
    exercise_index = int(parts[-1])
    patient_id = int(parts[-2])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
    if not plan:
        await call.answer("План не найден.", show_alert=True)
        return
    try:
        current = plan.exercises_json["exercises"][exercise_index].get("sets", "—")
    except IndexError:
        await call.answer("❌ Упражнение не найдено.", show_alert=True)
        return
    await state.update_data(
        patient_id=patient_id,
        exercise_index=exercise_index,
        edit_target="sets"
    )
    await state.set_state(EditPlanFSM.waiting_for_sets)
    await call.message.answer(
        f"Введите новое количество подходов.\nПрежнее значение: {current}",
        reply_markup=back_kb()
    )
    await call.answer()


# --- ЗАПРОС НОВОГО ЗНАЧЕНИЯ ПОВТОРЕНИЙ ---
@router.callback_query(F.data.startswith("edit_reps_"))
async def cb_edit_reps(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    # формат: edit_reps_{patient_id}_{exercise_index}
    exercise_index = int(parts[-1])
    patient_id = int(parts[-2])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
    if not plan:
        await call.answer("План не найден.", show_alert=True)
        return
    try:
        current = plan.exercises_json["exercises"][exercise_index].get("reps", "—")
    except IndexError:
        await call.answer("❌ Упражнение не найдено.", show_alert=True)
        return
    await state.update_data(
        patient_id=patient_id,
        exercise_index=exercise_index,
        edit_target="reps"
    )
    await state.set_state(EditPlanFSM.waiting_for_reps)
    await call.message.answer(
        f"Введите новое количество повторений.\nПрежнее значение: {current}",
        reply_markup=back_kb()
    )
    await call.answer()


# --- СОХРАНЕНИЕ НОВОГО ЗНАЧЕНИЯ ПОДХОДОВ / ПОВТОРЕНИЙ ---
@router.message(EditPlanFSM.waiting_for_sets)
@router.message(EditPlanFSM.waiting_for_reps)
async def process_exercise_param(message: Message, state: FSMContext):
    raw = message.text.strip()

    if not raw.isdigit() or int(raw) < 1:
        await message.answer(
            "❌ Некорректное значение. Введите целое число больше нуля. Повторите ввод:",
            reply_markup=back_kb()
        )
        return  # не сбрасываем FSM — ждём корректного ввода

    new_value = int(raw)

    data = await state.get_data()
    patient_id     = data.get("patient_id")
    exercise_index = data.get("exercise_index")
    edit_target    = data.get("edit_target")
    await state.clear()

    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await message.answer("❌ План не найден.", reply_markup=ReplyKeyboardRemove())
            await _send_main_menu(message)
            return

        new_exercises_json = copy.deepcopy(plan.exercises_json)
        try:
            new_exercises_json["exercises"][exercise_index][edit_target] = new_value
        except IndexError:
            await message.answer("❌ Упражнение не найдено.", reply_markup=ReplyKeyboardRemove())
            await _send_main_menu(message)
            return

        plan.exercises_json = new_exercises_json
        flag_modified(plan, "exercises_json")
        await session.commit()
        await session.refresh(plan)
        formatted_text = format_rehab_plan_text(plan.exercises_json, plan.nutrition_json)

    await message.answer("✅ Значение обновлено.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        f"📋 *Обновлённый план*\n\n{formatted_text}",
        reply_markup=get_edit_plan_kb(patient_id, status="draft"),
        parse_mode="Markdown"
    )


# --- МЕНЮ РЕДАКТИРОВАНИЯ ПИТАНИЯ ---
@router.callback_query(F.data.startswith("edit_nutrition_menu_"))
async def cb_edit_nutrition_menu(call: CallbackQuery):
    patient_id = int(call.data.split("edit_nutrition_menu_")[1])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        meals = plan.nutrition_json.get("nutrition", {}).get("meals", {}) if plan else None
    await call.message.edit_text(
        "Выберите приём пищи для редактирования:",
        reply_markup=nutrition_menu_kb(patient_id, meals)
    )
    await call.answer()


# --- ВЫБОР ПРИЁМА ПИЩИ ---
@router.callback_query(F.data.startswith("edit_meal_"))
async def cb_edit_meal(call: CallbackQuery):
    # edit_meal_food_ обрабатывается отдельным обработчиком cb_edit_meal_food
    if call.data.startswith("edit_meal_food_"):
        return
    suffix = call.data[len("edit_meal_"):]
    meal_key, raw_id = suffix.rsplit("_", 1)
    patient_id = int(raw_id)
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await call.answer("План не найден.", show_alert=True)
            return
    meal_name = MEAL_NAMES_RU.get(meal_key, meal_key.capitalize())
    await call.message.edit_text(
        f"Приём пищи: *{meal_name}*\nВыберите действие:",
        reply_markup=meal_actions_kb(meal_key, patient_id),
        parse_mode="Markdown"
    )
    await call.answer()
    
@router.callback_query(F.data.startswith("edit_meal_food_"))
async def cb_edit_meal_food(call: CallbackQuery, state: FSMContext):
    # формат: edit_meal_food_{meal_key}_{patient_id}
    suffix = call.data[len("edit_meal_food_"):]
    meal_key, raw_id = suffix.rsplit("_", 1)
    patient_id = int(raw_id)
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await call.answer("План не найден.", show_alert=True)
            return
        meals = plan.nutrition_json.get("nutrition", {}).get("meals", {})
        current = meals.get(meal_key, "Не задано")
    await state.update_data(patient_id=patient_id, meal_key=meal_key)
    await state.set_state(EditPlanFSM.waiting_for_meal)
    await call.message.answer(
        f"Введите новые блюда.\nСтарые блюда: {current}",
        reply_markup=back_kb()
    )
    await call.answer()
    
@router.callback_query(F.data.startswith("delete_meal_"))
async def cb_delete_meal(call: CallbackQuery, state: FSMContext):
    suffix = call.data[len("delete_meal_"):]
    meal_key, raw_id = suffix.rsplit("_", 1)
    patient_id = int(raw_id)
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await call.answer("План не найден.", show_alert=True)
            return
        meals = plan.nutrition_json.get("nutrition", {}).get("meals", {})
        if meal_key not in meals:
            await call.answer("Приём пищи уже удалён.", show_alert=True)
            return
        del meals[meal_key]
        plan.nutrition_json["nutrition"]["meals"] = meals
        flag_modified(plan, "nutrition_json")
        await session.commit()
    await state.clear()
    await call.message.answer(
        "✅ Приём пищи успешно удалён.",
        reply_markup=ReplyKeyboardRemove()
    )
    await call.message.answer(
        "Выберите приём пищи для редактирования:",
        reply_markup=nutrition_menu_kb(patient_id, meals)
    )
    await call.answer()


# --- СОХРАНЕНИЕ НОВОГО МЕНЮ ---
@router.message(EditPlanFSM.waiting_for_meal)
async def process_meal_input(message: Message, state: FSMContext):
    data = await state.get_data()
    patient_id = data.get("patient_id")
    meal_key   = data.get("meal_key")
    await state.clear()

    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await message.answer("❌ План не найден.", reply_markup=ReplyKeyboardRemove())
            await _send_main_menu(message)
            return

        new_nutrition_json = copy.deepcopy(plan.nutrition_json)
        if "nutrition" not in new_nutrition_json:
            new_nutrition_json["nutrition"] = {}
        if "meals" not in new_nutrition_json["nutrition"]:
            new_nutrition_json["nutrition"]["meals"] = {}

        new_nutrition_json["nutrition"]["meals"][meal_key] = message.text
        plan.nutrition_json = new_nutrition_json
        flag_modified(plan, "nutrition_json")
        await session.commit()
        await session.refresh(plan)
        formatted_text = format_rehab_plan_text(plan.exercises_json, plan.nutrition_json)

    await message.answer("✅ Меню обновлено.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        f"📋 *Обновлённый план*\n\n{formatted_text}",
        reply_markup=get_edit_plan_kb(patient_id, status="draft"),
        parse_mode="Markdown"
    )


# --- КНОПКА "НАЗАД К ПЛАНУ" ---
@router.callback_query(F.data.startswith("back_to_plan_"))
async def cb_back_to_plan(call: CallbackQuery):
    patient_id = int(call.data.split("back_to_plan_")[1])
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
    if not plan:
        await call.answer("План не найден.", show_alert=True)
        return
    formatted_text = format_rehab_plan_text(plan.exercises_json, plan.nutrition_json)
    status_ru = "✅ Активен" if plan.status == "active" else "📝 Черновик"
    text = f"📋 *План реабилитации*\nСтатус: {status_ru}\n\n{formatted_text}"
    await call.message.edit_text(
        text,
        reply_markup=get_edit_plan_kb(
            patient_id,
            status=plan.status,
            show_back_button=True
        ),
        parse_mode="Markdown"
    )
    await call.answer()
    
    
    # --- УДАЛЕНИЕ УПРАЖНЕНИЯ ---
@router.callback_query(F.data.startswith("delete_exercise_"))
async def cb_delete_exercise(call: CallbackQuery):
    parts = call.data.split("_")
    exercise_index = int(parts[-1])
    patient_id = int(parts[-2])

    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await call.answer("❌ План не найден.", show_alert=True)
            return

        new_exercises_json = copy.deepcopy(plan.exercises_json)
        exercises = new_exercises_json.get("exercises", [])

        try:
            deleted_name = exercises[exercise_index]["name"]
            exercises.pop(exercise_index)
        except IndexError:
            await call.answer("❌ Упражнение не найдено.", show_alert=True)
            return

        new_exercises_json["exercises"] = exercises
        plan.exercises_json = new_exercises_json
        flag_modified(plan, "exercises_json")
        await session.commit()
        await session.refresh(plan)
        updated_exercises = plan.exercises_json.get("exercises", [])

    await call.message.edit_text(
        f"✅ Упражнение «{deleted_name}» удалено.\n\nВыберите упражнение для редактирования:",
        reply_markup=exercises_list_kb(patient_id, updated_exercises)
    )
    await call.answer()


# --- ДОБАВЛЕНИЕ УПРАЖНЕНИЯ: шаг 1 — старт ---
@router.callback_query(F.data.startswith("add_exercise_"))
async def cb_add_exercise_start(call: CallbackQuery, state: FSMContext):
    patient_id = int(call.data.split("add_exercise_")[1])
    await state.update_data(patient_id=patient_id)
    await state.set_state(EditPlanFSM.add_exercise_name)
    await call.message.answer(
        "Введите название нового упражнения:",
        reply_markup=back_kb()
    )
    await call.answer()


# --- ДОБАВЛЕНИЕ УПРАЖНЕНИЯ: шаг 2 — название ---
@router.message(EditPlanFSM.add_exercise_name)
async def process_add_exercise_name(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(new_exercise_name=result)
    await state.set_state(EditPlanFSM.add_exercise_desc)
    await message.answer(
        "Введите описание упражнения (как выполнять):",
        reply_markup=back_kb()
    )
    
@router.message(EditPlanFSM.add_exercise_desc)
async def process_add_exercise_desc(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
    await state.update_data(new_exercise_desc=result)
    await state.set_state(EditPlanFSM.add_exercise_sets)
    await message.answer(
        "Введите количество подходов (целое число больше 0):",
        reply_markup=back_kb()
    )


# --- ДОБАВЛЕНИЕ УПРАЖНЕНИЯ: шаг 3 — подходы ---
@router.message(EditPlanFSM.add_exercise_sets)
async def process_add_exercise_sets(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) < 1:
        await message.answer(
            "❌ Некорректное значение. Введите целое число больше нуля. Повторите ввод:",
            reply_markup=back_kb()
        )
        return
    await state.update_data(new_exercise_sets=int(raw))
    await state.set_state(EditPlanFSM.add_exercise_reps)
    await message.answer(
        "Введите количество повторений (целое число больше 0):",
        reply_markup=back_kb()
    )


# --- ДОБАВЛЕНИЕ УПРАЖНЕНИЯ: шаг 4 — повторения + сохранение ---
@router.message(EditPlanFSM.add_exercise_reps)
async def process_add_exercise_reps(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) < 1:
        await message.answer(
            "❌ Некорректное значение. Введите целое число больше нуля. Повторите ввод:",
            reply_markup=back_kb()
        )
        return

    data = await state.get_data()
    patient_id        = data.get("patient_id")
    new_exercise_name = data.get("new_exercise_name")
    new_exercise_sets = data.get("new_exercise_sets")
    new_exercise_reps = int(raw)
    await state.clear()

    new_exercise = {
        "name":        data.get("new_exercise_name"),
        "description": data.get("new_exercise_desc"),
        "sets":        data.get("new_exercise_sets"),
        "reps":        new_exercise_reps,
    }

    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if not plan:
            await message.answer("❌ План не найден.", reply_markup=ReplyKeyboardRemove())
            await _send_main_menu(message)
            return

        new_exercises_json = copy.deepcopy(plan.exercises_json)
        new_exercises_json["exercises"].append(new_exercise)
        plan.exercises_json = new_exercises_json
        flag_modified(plan, "exercises_json")
        await session.commit()
        await session.refresh(plan)
        updated_exercises = plan.exercises_json.get("exercises", [])

    await message.answer("✅ Упражнение добавлено.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Выберите упражнение для редактирования:",
        reply_markup=exercises_list_kb(patient_id, updated_exercises)
    )
    
@router.callback_query(F.data.startswith("add_meal_"))
async def cb_add_meal(call: CallbackQuery, state: FSMContext):
    patient_id = int(call.data.split("add_meal_")[1])
    await state.update_data(patient_id=patient_id)
    await state.set_state(EditPlanFSM.add_meal_name)
    await call.message.answer(
        "Введите название приёма пищи (только на русском):",
        reply_markup=back_kb()
    )
    await call.answer()


@router.message(EditPlanFSM.add_meal_name)
async def process_add_meal_name(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
        
    await state.update_data(new_meal_name=result.lower())
    await state.set_state(EditPlanFSM.add_meal_food)
    await message.answer(
        "Теперь введите блюда для этого приёма пищи (только на русском):",
        reply_markup=back_kb()
    )


@router.message(EditPlanFSM.add_meal_food)
async def process_add_meal_food(message: Message, state: FSMContext):
    valid, result = validate_russian_text(message.text)
    if not valid:
        await message.answer(result, reply_markup=back_kb())
        return
        
    data = await state.get_data()
    patient_id = data.get("patient_id")
    new_meal_name = data.get("new_meal_name")
    new_food = result
    
    await state.clear()
    
    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        if plan:
            if "nutrition" not in plan.nutrition_json:
                plan.nutrition_json["nutrition"] = {}
            if "meals" not in plan.nutrition_json["nutrition"]:
                plan.nutrition_json["nutrition"]["meals"] = {}
                
            plan.nutrition_json["nutrition"]["meals"][new_meal_name] = new_food
            # Принудительно помечаем поле как измененное для SQLAlchemy
            flag_modified(plan, "nutrition_json")
            await session.commit()
            
            # Получаем обновленный словарь приемов пищи
            meals = plan.nutrition_json["nutrition"]["meals"]
            
            await message.answer(
                f"✅ Приём пищи «{new_meal_name.capitalize()}» успешно добавлен.",
                reply_markup=ReplyKeyboardRemove()
            )
            await message.answer(
                "Выберите приём пищи для редактирования:",
                reply_markup=nutrition_menu_kb(patient_id, meals)
            )
        else:
            await message.answer("План не найден.", reply_markup=ReplyKeyboardRemove())
            await _send_main_menu(message)


# ===========================================================================
# ОДОБРЕНИЕ ПЛАНА
# ===========================================================================

@router.callback_query(F.data.startswith("approve_"))
async def process_approve(call: CallbackQuery, bot: Bot):
    patient_id = int(call.data.split("_")[1])

    async with async_session_maker() as session:
        plan = await crud.get_rehab_plan(session, patient_id)
        patient = await crud.get_patient(session, patient_id)
        plan.status = "active"
        await session.commit()
        chat_id = patient.chat_id
        username = patient.username

        # Формируем текст плана для отправки пациенту
        formatted_text = format_rehab_plan_text(
            plan.exercises_json,
            plan.nutrition_json
        )

    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer()

    plan_message = (
        f"🎉 Ваш план реабилитации утверждён врачом!\n\n"
        f"{formatted_text}"
    )

    if chat_id:
        try:
            await bot.send_message(
                chat_id,
                plan_message,
                parse_mode="Markdown"
            )
            await call.message.answer(
                f"✅ План утвержден и мгновенно отправлен пациенту @{username}!"
            )
        except Exception:
            await call.message.answer(
                f"✅ План утвержден!\n"
                f"⚠️ Пациент @{username} заблокировал бота. "
                f"План будет показан автоматически если пациент "
                f"разблокирует бота."
            )
    else:
        await call.message.answer(
            f"✅ План утвержден и сохранён!\n\n"
            f"📋 Пациент @{username} ещё не запустил бота. "
            f"Как только он введёт /start — план автоматически "
            f"появится у него в боте."
        )

    await _send_main_menu(call.message)
    
    
@router.message()
async def unknown_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    await message.answer(
        "⚠️ Неизвестная команда. Воспользуйтесь кнопками меню:"
    )
    await _send_main_menu(message)