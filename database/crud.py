from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import Doctor, Patient, RehabPlan, MedicationPlan, Admin
from sqlalchemy.orm.attributes import flag_modified
from database.models import MedicationPlan  # Добавь к уже существующим импортам моделей
from sqlalchemy.exc import IntegrityError  # добавить в импорты


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

async def get_user_role(session: AsyncSession, username: str) -> str | None:
    username = username.strip().lower().replace('@', '')  # добавить эту строку вверху
    if await session.scalar(select(Admin).where(Admin.username == username)):
        return 'admin'
    if await session.scalar(select(Doctor).where(Doctor.username == username)):
        return 'doctor'
    if await session.scalar(select(Patient).where(Patient.username == username)):
        return 'patient'
    return None

async def add_doctor(session: AsyncSession, username: str, fio: str):
    doctor = Doctor(username=username, fio=fio)
    session.add(doctor)
    await session.commit()

async def get_doctor_by_username(session: AsyncSession, username: str) -> Doctor | None:
    return await session.scalar(select(Doctor).where(Doctor.username == username))

