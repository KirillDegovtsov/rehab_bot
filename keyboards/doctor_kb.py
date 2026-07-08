from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def back_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить пациента", callback_data="menu_add_patient")
    builder.button(text="📋 Список пациентов", callback_data="menu_patients_list")
    builder.adjust(1)
    return builder.as_markup()


def gender_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👨 Мужской", callback_data="gender_male")
    builder.button(text="👩 Женский", callback_data="gender_female")
    builder.adjust(2)
    return builder.as_markup()


def patient_list_kb(patients) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in patients:
        builder.button(text=p.name, callback_data=f"patient_card_{p.id}")
    builder.button(text="🔙 Главное меню", callback_data="menu_back")
    builder.adjust(1)
    return builder.as_markup()


def patient_card_kb(patient_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Редактировать данные", callback_data=f"edit_pat_{patient_id}")
    builder.button(text="📋 Редактировать план",   callback_data=f"view_plan_{patient_id}")
    builder.button(text="❌ Удалить пациента",      callback_data=f"delete_pat_{patient_id}")
    builder.button(text="🔙 К списку",             callback_data="back_to_list")
    builder.adjust(1)
    return builder.as_markup()


def edit_patient_fields_kb(patient_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 ФИО",                  callback_data=f"epat_name_{patient_id}")
    builder.button(text="⚧ Пол",                  callback_data=f"epat_gender_{patient_id}")
    builder.button(text="🔢 Возраст",              callback_data=f"epat_age_{patient_id}")
    builder.button(text="🏥 Диагноз",              callback_data=f"epat_diagnosis_{patient_id}")
    builder.button(text="📅 Дата операции",        callback_data=f"epat_surgery_date_{patient_id}")
    builder.button(text="🦴 Тип перелома",         callback_data=f"epat_fracture_{patient_id}")
    builder.button(text="⚕️ Метод операции",       callback_data=f"epat_method_{patient_id}")
    builder.button(text="💊 Сопут. заболевания",   callback_data=f"epat_comorbid_{patient_id}")
    builder.button(text="❤️ Состояние здоровья",   callback_data=f"epat_health_{patient_id}")
    builder.button(text="📱 Telegram username",    callback_data=f"epat_username_{patient_id}")
    builder.button(text="❌ Отмена",               callback_data=f"epat_cancel_{patient_id}")
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def get_edit_plan_kb(
    patient_id: int,
    status: str = "draft",
    show_back_button: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if status != "active":
        builder.button(text="✅ Одобрить план",        callback_data=f"approve_{patient_id}")
        builder.button(text="🏋️ Изменить упражнения",  callback_data=f"edit_exercises_menu_{patient_id}")
        builder.button(text="🍽️ Изменить питание",     callback_data=f"edit_nutrition_menu_{patient_id}")
        builder.adjust(1)
    
    if show_back_button:
        builder.button(text="🔙 Назад к пациенту", callback_data=f"patient_card_{patient_id}")
        builder.adjust(1)

    return builder.as_markup()


def exercises_list_kb(patient_id: int, exercises: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, exercise in enumerate(exercises):
        name = exercise.get("name", f"Упражнение {index + 1}")
        builder.button(text=name, callback_data=f"select_exercise_{patient_id}_{index}")
    builder.button(text="➕ Добавить упражнение", callback_data=f"add_exercise_{patient_id}")
    builder.button(text="🔙 Назад",               callback_data=f"back_to_plan_{patient_id}")
    builder.adjust(1)
    return builder.as_markup()


def exercise_edit_kb(patient_id: int, exercise_index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Подходы",    callback_data=f"edit_sets_{patient_id}_{exercise_index}")
    builder.button(text="🔁 Повторения", callback_data=f"edit_reps_{patient_id}_{exercise_index}")
    builder.button(text="🗑️ Удалить",    callback_data=f"delete_exercise_{patient_id}_{exercise_index}")
    builder.button(text="🔙 Назад",      callback_data=f"edit_exercises_menu_{patient_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def nutrition_menu_kb(patient_id: int) -> InlineKeyboardMarkup:
    """Кнопки выбора приёма пищи для редактирования."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🍳 Завтрак", callback_data=f"edit_meal_breakfast_{patient_id}")
    builder.button(text="🥗 Обед",    callback_data=f"edit_meal_lunch_{patient_id}")
    builder.button(text="🍲 Ужин",    callback_data=f"edit_meal_dinner_{patient_id}")
    builder.button(text="🔙 Назад",   callback_data=f"back_to_plan_{patient_id}")
    builder.adjust(1)
    return builder.as_markup()

def confirm_generation_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Сгенерировать план", callback_data="confirm_generate_plan")
    builder.adjust(1)
    return builder.as_markup()