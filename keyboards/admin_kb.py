from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from typing import Sequence, Any

class AdminDoctorCallback(CallbackData, prefix="adm_doc"):
    action: str
    doctor_id: int = 0
    field: str = ""

def admin_main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить врача", callback_data="admin_add_doctor")
    builder.button(text="📋 Список врачей", callback_data="admin_doctors_list")
    builder.adjust(1)
    return builder.as_markup()

def doctors_list_kb(doctors: Sequence[Any]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for doc in doctors:
        builder.button(
            text=f"👨‍⚕️ {doc.fio}",
            callback_data=AdminDoctorCallback(action="view", doctor_id=doc.id).pack()
        )
    builder.button(text="🔙 В главное меню", callback_data="admin_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def doctor_card_kb(doctor_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Изменить username",
        callback_data=AdminDoctorCallback(action="edit", doctor_id=doctor_id, field="username").pack()
    )
    builder.button(
        text="✏️ Изменить ФИО",
        callback_data=AdminDoctorCallback(action="edit", doctor_id=doctor_id, field="fio").pack()
    )
    builder.button(text="🔙 К списку врачей", callback_data="admin_doctors_list")
    builder.adjust(1)
    return builder.as_markup()

def back_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )