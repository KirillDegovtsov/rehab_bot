from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

def patient_main_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="Подтвердить план")
    builder.button(text="Изменить план")
    builder.button(text="Задать вопрос ассистенту")
    builder.button(text="Мой прогресс")
    builder.button(text="Напоминания")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def disclaimer_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Понял(а), принимаю условия", callback_data="disclaimer_accept")
    return builder.as_markup()

def pain_scale_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(11):
        builder.button(text=str(i), callback_data=f"pain_{i}")
    builder.adjust(6, 5) # Распределение: 6 кнопок в первом ряду, 5 во втором
    return builder.as_markup()

def mobility_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Лежу", callback_data="mob_lie")
    builder.button(text="Передвигаюсь на костылях", callback_data="mob_crutches")
    builder.button(text="Хожу самостоятельно", callback_data="mob_walk")
    builder.adjust(1)
    return builder.as_markup()

def workout_rating_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="1 - Было очень легко", callback_data="workout_rating_1")
    builder.button(text="2", callback_data="workout_rating_2")
    builder.button(text="3", callback_data="workout_rating_3")
    builder.button(text="4", callback_data="workout_rating_4")
    builder.button(text="5 - Было очень тяжело", callback_data="workout_rating_5")
    builder.adjust(1, 3, 1)
    return builder.as_markup()

def recommendation_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Согласен", callback_data="recom_accept")
    builder.button(text="Не сейчас", callback_data="recom_decline")
    builder.adjust(2)
    return builder.as_markup()

def meal_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Верно", callback_data="meal_correct")
    builder.button(text="Исправить", callback_data="meal_fix")
    builder.adjust(2)
    return builder.as_markup()