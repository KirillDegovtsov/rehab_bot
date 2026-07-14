from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, StateFilter
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from keyboards.admin_kb import (
    admin_main_menu_kb, 
    doctors_list_kb, 
    doctor_card_kb, 
    back_kb, 
    AdminDoctorCallback
)
from database import crud

router = Router()

class AdminNavigationFSM(StatesGroup):
    main_menu = State()
    doctors_list = State()
    doctor_card = State()

class AddDoctorFSM(StatesGroup):
    username = State()
    fio = State()

class EditDoctorFSM(StatesGroup):
    waiting_value = State()


@router.message(F.text == "🔙 Назад", StateFilter(AddDoctorFSM, EditDoctorFSM))
async def process_admin_back_button(
    message: Message, 
    state: FSMContext, 
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    current_state = await state.get_state()

    if current_state == AddDoctorFSM.username.state:
        await state.clear()
        await state.set_state(AdminNavigationFSM.main_menu)
        await message.answer("Главное меню:", reply_markup=ReplyKeyboardRemove())
        await message.answer("Выберите действие:", reply_markup=admin_main_menu_kb())

    elif current_state == AddDoctorFSM.fio.state:
        await state.set_state(AddDoctorFSM.username)
        await message.answer("Введите username врача (без @):", reply_markup=back_kb())

    elif current_state == EditDoctorFSM.waiting_value.state:
        data = await state.get_data()
        doctor_id = data.get("doctor_id")
        await state.set_state(AdminNavigationFSM.doctor_card)
        
        async with session_maker() as session:
            doctor = await crud.get_doctor_by_id(session, doctor_id)
            
        text = f"👨‍⚕️ Врач: {doctor.fio}\nID: {doctor.id}\nUsername: @{doctor.username}"
        
        await message.answer("Отмена редактирования.", reply_markup=ReplyKeyboardRemove())
        await message.answer(text, reply_markup=doctor_card_kb(doctor_id))


@router.message(Command("start"))
async def admin_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminNavigationFSM.main_menu)
    await message.answer("Добро пожаловать в панель администратора.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=admin_main_menu_kb())


@router.callback_query(F.data == "admin_main_menu")
async def cq_admin_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminNavigationFSM.main_menu)
    await callback.message.edit_text("Выберите действие:", reply_markup=admin_main_menu_kb())


@router.callback_query(F.data == "admin_doctors_list")
async def cq_doctors_list(
    callback: CallbackQuery, 
    state: FSMContext, 
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await state.set_state(AdminNavigationFSM.doctors_list)
    
    async with session_maker() as session:
        doctors = await crud.get_all_doctors(session)

    if not doctors:
        await callback.answer("Список врачей пуст", show_alert=True)
        return

    await callback.message.edit_text("Список врачей:", reply_markup=doctors_list_kb(doctors))


@router.callback_query(AdminDoctorCallback.filter(F.action == "view"))
async def cq_doctor_card(
    callback: CallbackQuery, 
    callback_data: AdminDoctorCallback, 
    state: FSMContext, 
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await state.set_state(AdminNavigationFSM.doctor_card)
    await state.update_data(doctor_id=callback_data.doctor_id)

    async with session_maker() as session:
        doctor = await crud.get_doctor_by_id(session, callback_data.doctor_id)
        
    text = f"👨‍⚕️ Врач: {doctor.fio}\nID: {doctor.id}\nUsername: @{doctor.username}"
    await callback.message.edit_text(text, reply_markup=doctor_card_kb(doctor_id=doctor.id))


@router.callback_query(F.data == "admin_add_doctor")
async def cq_add_doctor_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddDoctorFSM.username)
    await callback.message.delete()
    await callback.message.answer("Введите username нового врача (без @):", reply_markup=back_kb())


@router.message(StateFilter(AddDoctorFSM.username), F.text)
async def process_add_doctor_username(
    message: Message, 
    state: FSMContext, 
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    username = message.text.replace("@", "").strip()

    async with session_maker() as session:
        is_exists = await crud.check_username_exists(session, username)
        
    if is_exists:
        await message.answer("⚠️ Этот username уже зарегистрирован. Введите другой:")
        return

    await state.update_data(new_doc_username=username)
    await state.set_state(AddDoctorFSM.fio)
    await message.answer("Введите ФИО врача:", reply_markup=back_kb())


@router.message(StateFilter(AddDoctorFSM.fio), F.text)
async def process_add_doctor_fio(
    message: Message, 
    state: FSMContext, 
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    fio = message.text.strip()
    if not fio:
        await message.answer("⚠️ ФИО не может быть пустым. Повторите ввод:")
        return

    data = await state.get_data()
    username = data["new_doc_username"]

    async with session_maker() as session:
        await crud.create_doctor(session, username=username, fio=fio)

    await state.clear()
    await state.set_state(AdminNavigationFSM.main_menu)
    await message.answer("✅ Врач успешно добавлен!", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=admin_main_menu_kb())


@router.callback_query(AdminDoctorCallback.filter(F.action == "edit"))
async def cq_edit_doctor_start(
    callback: CallbackQuery, 
    callback_data: AdminDoctorCallback, 
    state: FSMContext
) -> None:
    await state.set_state(EditDoctorFSM.waiting_value)
    await state.update_data(edit_field=callback_data.field, doctor_id=callback_data.doctor_id)

    field_name = "username (без @)" if callback_data.field == "username" else "ФИО"
    await callback.message.delete()
    await callback.message.answer(f"Введите новое значение для {field_name}:", reply_markup=back_kb())


@router.message(StateFilter(EditDoctorFSM.waiting_value), F.text)
async def process_edit_doctor_value(
    message: Message, 
    state: FSMContext, 
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    data = await state.get_data()
    field = data["edit_field"]
    doctor_id = data["doctor_id"]
    new_value = message.text.strip()

    if field == "username":
        new_value = new_value.replace("@", "")
        async with session_maker() as session:
            is_exists = await crud.check_username_exists(session, new_value, exclude_id=doctor_id)
        if is_exists:
            await message.answer("⚠️ Этот username уже занят. Введите другой:")
            return

    if field == "fio" and not new_value:
        await message.answer("⚠️ ФИО не может быть пустым. Введите корректное ФИО:")
        return

    async with session_maker() as session:
        await crud.update_doctor_field(session, doctor_id, field, new_value)
        doctor = await crud.get_doctor_by_id(session, doctor_id)

    await state.set_state(AdminNavigationFSM.doctor_card)
    text = f"👨‍⚕️ Врач: {doctor.fio}\nID: {doctor.id}\nUsername: @{doctor.username}"
    
    await message.answer("✅ Данные успешно обновлены!", reply_markup=ReplyKeyboardRemove())
    await message.answer(text, reply_markup=doctor_card_kb(doctor_id))


# Обновленный обработчик неизвестных сообщений с возвратом кнопок
@router.message(StateFilter(
    AdminNavigationFSM.main_menu, 
    AdminNavigationFSM.doctors_list, 
    AdminNavigationFSM.doctor_card
))
async def process_unknown_message(
    message: Message, 
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession]
) -> None:
    try:
        await message.delete()
    except Exception:
        pass  

    current_state = await state.get_state()
    warning_text = "⚠️ Пожалуйста, используйте кнопки меню.\n\n"

    # Заново отрисовываем меню в зависимости от текущего стейта
    if current_state == AdminNavigationFSM.main_menu.state:
        await message.answer(warning_text + "Выберите действие:", reply_markup=admin_main_menu_kb())
        
    elif current_state == AdminNavigationFSM.doctors_list.state:
        async with session_maker() as session:
            doctors = await crud.get_all_doctors(session)
        await message.answer(warning_text + "Список врачей:", reply_markup=doctors_list_kb(doctors))
        
    elif current_state == AdminNavigationFSM.doctor_card.state:
        data = await state.get_data()
        doctor_id = data.get("doctor_id")
        if doctor_id:
            async with session_maker() as session:
                doctor = await crud.get_doctor_by_id(session, doctor_id)
            text = f"{warning_text}👨‍⚕️ Врач: {doctor.fio}\nID: {doctor.id}\nUsername: @{doctor.username}"
            await message.answer(text, reply_markup=doctor_card_kb(doctor_id))