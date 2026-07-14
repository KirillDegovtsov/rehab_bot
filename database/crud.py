from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import Doctor, Patient, RehabPlan, MedicationPlan, Admin
from sqlalchemy.orm.attributes import flag_modified
from database.models import MedicationPlan  # Добавь к уже существующим импортам моделей
from sqlalchemy.exc import IntegrityError  # добавить в импорты

import logging
from datetime import time
from typing import Optional, Sequence, Dict

from sqlalchemy import update, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from database.models import UserReminder, PainLog, MealLog, WorkoutLog

logger = logging.getLogger(__name__)


async def get_or_create_doctor(
    session: AsyncSession, tg_id: int, fio: str, username: str
) -> Doctor:
    # 1. Ищем по telegram_id (повторный /start)
    doctor = await session.scalar(
        select(Doctor).where(Doctor.telegram_id == tg_id)
    )

    # 2. Если не нашли — ищем по username (врач добавлен админом, ещё не логинился)
    if not doctor:
        doctor = await session.scalar(
            select(Doctor).where(Doctor.username == username)
        )

    if doctor:
        # Обновляем поля, которые могли быть пустыми при создании через admin
        updated = False
        if doctor.telegram_id is None and tg_id:
            doctor.telegram_id = tg_id
            updated = True
        if not doctor.fio and fio:
            doctor.fio = fio
            updated = True
        if updated:
            await session.commit()
        return doctor

    # 3. Врача нет вообще — создаём (защита от гонок через try/except)
    try:
        doctor = Doctor(username=username, telegram_id=tg_id, fio=fio)
        session.add(doctor)
        await session.commit()
        return doctor
    except IntegrityError:
        await session.rollback()
        # Кто-то успел вставить между SELECT и INSERT — просто читаем
        doctor = await session.scalar(
            select(Doctor).where(Doctor.username == username)
        )
        return doctor


async def create_patient(session: AsyncSession, doctor_id: int, patient_data: dict) -> Patient:
    patient = Patient(doctor_id=doctor_id, **patient_data)
    session.add(patient)
    await session.commit()
    await session.refresh(patient)
    return patient


async def create_or_update_rehab_plan(
    session: AsyncSession,
    patient_id: int,
    plan_data: dict,
    status: str = 'draft'
) -> RehabPlan:
    stmt = select(RehabPlan).where(RehabPlan.patient_id == patient_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if plan:
        plan.exercises_json = plan_data.get('exercises_json', plan.exercises_json)
        plan.nutrition_json = plan_data.get('nutrition_json', plan.nutrition_json)
        plan.status = status
    else:
        plan = RehabPlan(
            patient_id=patient_id,
            exercises_json=plan_data['exercises_json'],
            nutrition_json=plan_data['nutrition_json'],
            status=status
        )
        session.add(plan)

    await session.commit()
    await session.refresh(plan)
    return plan


async def get_rehab_plan(session: AsyncSession, patient_id: int) -> RehabPlan:
    stmt = select(RehabPlan).where(RehabPlan.patient_id == patient_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_patients_by_doctor(session: AsyncSession, doctor_id: int):
    stmt = select(Patient).where(Patient.doctor_id == doctor_id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_patient(session: AsyncSession, patient_id: int) -> Patient:
    stmt = select(Patient).where(Patient.id == patient_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_patient(session: AsyncSession, patient_id: int):
    patient = await get_patient(session, patient_id)
    if patient:
        await session.delete(patient)
        await session.commit()


async def update_patient(
    session: AsyncSession,
    patient_id: int,
    update_data: dict
) -> Patient:
    patient = await get_patient(session, patient_id)
    if patient:
        for key, value in update_data.items():
            setattr(patient, key, value)
        await session.commit()
        await session.refresh(patient)
    return patient


async def get_patient_by_username(
    session: AsyncSession,
    username: str
) -> Patient:
    stmt = select(Patient).where(Patient.username == username)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_medication_plan(session: AsyncSession, patient_id: int):
    stmt = select(MedicationPlan).where(MedicationPlan.patient_id == patient_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def create_medication_plan(session: AsyncSession, patient_id: int) -> MedicationPlan:
    plan = MedicationPlan(patient_id=patient_id, medications=[])
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan

async def add_medication(session: AsyncSession, patient_id: int, medication: dict) -> MedicationPlan:
    plan = await get_medication_plan(session, patient_id)
    if not plan:
        plan = await create_medication_plan(session, patient_id)
    new_list = list(plan.medications) + [medication]
    plan.medications = new_list
    flag_modified(plan, "medications")
    await session.commit()
    await session.refresh(plan)
    return plan

async def update_medications(session: AsyncSession, patient_id: int, new_list: list) -> MedicationPlan:
    plan = await get_medication_plan(session, patient_id)
    plan.medications = new_list
    flag_modified(plan, "medications")
    await session.commit()
    return plan


async def bootstrap_admin(session: AsyncSession, admin_username: str):
    username_clean = admin_username.strip().lower().replace('@', '')  # добавлен .strip()
    admin = await session.scalar(select(Admin).where(Admin.username == username_clean))
    if not admin:
        admin = Admin(username=username_clean)
        session.add(admin)
        await session.commit()

# --- ОБНОВИТЬ: добавить поиск по tg_id в get_user_role ---
# В текущей версии используется telegram_id — меняем на tg_id везде

async def get_user_role(session: AsyncSession, tg_id: int) -> Optional[str]:
    """Определение роли пользователя по tg_id"""
    admin = await session.scalar(select(Admin).where(Admin.tg_id == tg_id))
    if admin:
        return "admin"
    
    doctor = await session.scalar(select(Doctor).where(Doctor.tg_id == tg_id))
    if doctor:
        return "doctor"
    
    patient = await session.scalar(select(Patient).where(Patient.tg_id == tg_id))
    if patient:
        return "patient"
    
    return None

async def add_doctor(session: AsyncSession, username: str, fio: str):
    doctor = Doctor(username=username, fio=fio)
    session.add(doctor)
    await session.commit()

async def get_doctor_by_username(session: AsyncSession, username: str) -> Doctor | None:
    return await session.scalar(select(Doctor).where(Doctor.username == username))



# Добавьте эти функции в конец файла database/crud.py

async def get_all_doctors(session: AsyncSession):
    """Получает список всех врачей из БД."""
    result = await session.execute(select(Doctor))
    return result.scalars().all()


async def get_doctor_by_id(session: AsyncSession, doctor_id: int) -> Doctor | None:
    """Получает врача по ID."""
    result = await session.execute(select(Doctor).where(Doctor.id == doctor_id))
    return result.scalar_one_or_none()


async def check_username_exists(session: AsyncSession, username: str, exclude_id: int = None) -> bool:
    """Проверяет, занят ли username врачом, пациентом или админом."""
    clean_username = username.strip().lower().replace('@', '')
    
    # Ищем врача с таким username
    doc_stmt = select(Doctor).where(Doctor.username == clean_username)
    if exclude_id:
        doc_stmt = doc_stmt.where(Doctor.id != exclude_id)
        
    doc = await session.scalar(doc_stmt)
    if doc:
        return True
        
    # Также проверим, что username не занят админом или пациентом
    if await session.scalar(select(Admin).where(Admin.username == clean_username)):
        return True
    if await session.scalar(select(Patient).where(Patient.username == clean_username)):
        return True
        
    return False


async def create_doctor(session: AsyncSession, username: str, fio: str) -> Doctor:
    """Создает нового врача (замена add_doctor для консистентности)."""
    clean_username = username.strip().lower().replace('@', '')
    doctor = Doctor(username=clean_username, fio=fio)
    session.add(doctor)
    await session.commit()
    await session.refresh(doctor)
    return doctor


async def update_doctor_field(session: AsyncSession, doctor_id: int, field: str, new_value: str) -> None:
    """Обновляет определенное поле врача."""
    doctor = await get_doctor_by_id(session, doctor_id)
    if doctor:
        if field == "username":
            setattr(doctor, field, new_value.strip().lower().replace('@', ''))
        else:
            setattr(doctor, field, new_value)
        await session.commit()
        


# ================================================================
# ПАЦИЕНТ: Онбординг и профиль
# ================================================================

async def get_patient_by_tg_id(session: AsyncSession, tg_id: int) -> Optional[Patient]:
    """
    Получение пациента по Telegram ID.
    Используется при каждом входе пациента для авторизации.
    """
    try:
        return await session.scalar(select(Patient).where(Patient.tg_id == tg_id))
    except SQLAlchemyError as e:
        logger.error(f"[get_patient_by_tg_id] tg_id={tg_id}: {e}")
        return None


async def update_patient_tg_id(session: AsyncSession, patient_id: int, tg_id: int) -> bool:
    """
    Привязка tg_id к профилю пациента.
    Вызывается один раз — когда пациент впервые нажимает /start,
    а врач уже добавил его в систему по username.
    """
    try:
        await session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(tg_id=tg_id)
        )
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[update_patient_tg_id] patient_id={patient_id}: {e}")
        return False


async def update_patient_onboarding_data(
    session: AsyncSession,
    patient_id: int,
    name: str,
    mobility: str
) -> bool:
    """
    Сохранение данных после прохождения онбординга:
    имя и уровень мобильности.
    Флагом завершения онбординга служит наличие записи в pain_logs.
    """
    try:
        await session.execute(
            update(Patient)
            .where(Patient.id == patient_id)
            .values(name=name, mobility=mobility)
        )
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[update_patient_onboarding_data] patient_id={patient_id}: {e}")
        return False


async def get_patient_full_profile(session: AsyncSession, patient_id: int) -> Optional[Patient]:
    """
    Получение пациента вместе со всеми его логами и напоминаниями.
    Используется в RAG-ассистенте для формирования контекста.
    selectinload — оптимальный метод для async SQLAlchemy 2.0,
    избегает проблем N+1 и lazy loading в async контексте.
    """
    try:
        stmt = (
            select(Patient)
            .where(Patient.id == patient_id)
            .options(
                selectinload(Patient.reminders),
                selectinload(Patient.pain_logs),
                selectinload(Patient.meal_logs),
                selectinload(Patient.workout_logs),
            )
        )
        return await session.scalar(stmt)
    except SQLAlchemyError as e:
        logger.error(f"[get_patient_full_profile] patient_id={patient_id}: {e}")
        return None


# ================================================================
# НАПОМИНАНИЯ (UserReminder)
# ================================================================

async def create_reminder(
    session: AsyncSession,
    patient_id: int,
    text: str,
    reminder_time: time
) -> Optional[UserReminder]:
    try:
        reminder = UserReminder(patient_id=patient_id, text=text, reminder_time=reminder_time)
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[create_reminder] patient_id={patient_id}: {e}")
        return None


async def get_active_reminders(session: AsyncSession, patient_id: int) -> Sequence[UserReminder]:
    try:
        stmt = (
            select(UserReminder)
            .where(
                UserReminder.patient_id == patient_id,
                UserReminder.is_active == True
            )
            .order_by(UserReminder.reminder_time)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"[get_active_reminders] patient_id={patient_id}: {e}")
        return []


async def deactivate_reminder(session: AsyncSession, reminder_id: int) -> bool:
    """
    Деактивация напоминания (soft delete).
    Предпочтительнее физического удаления — сохраняется история.
    """
    try:
        await session.execute(
            update(UserReminder)
            .where(UserReminder.id == reminder_id)
            .values(is_active=False)
        )
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[deactivate_reminder] reminder_id={reminder_id}: {e}")
        return False


async def delete_reminder(session: AsyncSession, reminder_id: int) -> bool:
    """Физическое удаление напоминания (например, по запросу пациента)"""
    try:
        await session.execute(delete(UserReminder).where(UserReminder.id == reminder_id))
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[delete_reminder] reminder_id={reminder_id}: {e}")
        return False


# ================================================================
# ЛОГИ БОЛИ (PainLog)
# ================================================================

async def add_pain_log(session: AsyncSession, patient_id: int, pain_level: int) -> Optional[PainLog]:
    try:
        log = PainLog(patient_id=patient_id, pain_level=pain_level)
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[add_pain_log] patient_id={patient_id}: {e}")
        return None


async def get_pain_logs(session: AsyncSession, patient_id: int, limit: int = 7) -> Sequence[PainLog]:
    """Последние N записей боли. Используется для отображения прогресса."""
    try:
        stmt = (
            select(PainLog)
            .where(PainLog.patient_id == patient_id)
            .order_by(PainLog.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"[get_pain_logs] patient_id={patient_id}: {e}")
        return []


async def has_pain_log(session: AsyncSession, patient_id: int) -> bool:
    """
    Проверка, прошел ли пациент онбординг.
    Флаг онбординга — наличие хотя бы одной записи боли.
    """
    try:
        stmt = select(PainLog.id).where(PainLog.patient_id == patient_id).limit(1)
        result = await session.scalar(stmt)
        return result is not None
    except SQLAlchemyError as e:
        logger.error(f"[has_pain_log] patient_id={patient_id}: {e}")
        return False


# ================================================================
# ЛОГИ ПИТАНИЯ (MealLog)
# ================================================================

async def add_meal_log(
    session: AsyncSession,
    patient_id: int,
    text: str,
    kbju: Dict[str, float]
) -> Optional[MealLog]:
    try:
        log = MealLog(
            patient_id=patient_id,
            original_text=text,
            calories=kbju.get("calories"),
            proteins=kbju.get("proteins"),
            fats=kbju.get("fats"),
            carbs=kbju.get("carbs"),
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[add_meal_log] patient_id={patient_id}: {e}")
        return None


async def get_meal_logs(session: AsyncSession, patient_id: int, limit: int = 10) -> Sequence[MealLog]:
    """Последние N записей питания для отображения в прогрессе."""
    try:
        stmt = (
            select(MealLog)
            .where(MealLog.patient_id == patient_id)
            .order_by(MealLog.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"[get_meal_logs] patient_id={patient_id}: {e}")
        return []


# ================================================================
# ЛОГИ ТРЕНИРОВОК (WorkoutLog)
# ================================================================

async def add_workout_log(
    session: AsyncSession,
    patient_id: int,
    rating: int,
    repetitions: int
) -> Optional[WorkoutLog]:
    try:
        log = WorkoutLog(patient_id=patient_id, rating=rating, repetitions=repetitions)
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f"[add_workout_log] patient_id={patient_id}: {e}")
        return None


async def get_workout_logs(session: AsyncSession, patient_id: int, limit: int = 7) -> Sequence[WorkoutLog]:
    """Последние N тренировок. Используется для отображения прогресса."""
    try:
        stmt = (
            select(WorkoutLog)
            .where(WorkoutLog.patient_id == patient_id)
            .order_by(WorkoutLog.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"[get_workout_logs] patient_id={patient_id}: {e}")
        return []