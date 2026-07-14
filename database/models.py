from datetime import datetime, time
from typing import Optional, List

from sqlalchemy import BigInteger, String, Integer, ForeignKey, DateTime, Time, Float, Boolean, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# --- Роли персонала ---

class Admin(Base):
    __tablename__ = "admins"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Doctor(Base):
    __tablename__ = "doctors"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Связь с пациентами
    patients: Mapped[List["Patient"]] = relationship("Patient", back_populates="doctor", cascade="all, delete-orphan")


# --- Пациенты и их планы ---

class Patient(Base):
    __tablename__ = "patients"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # tg_id может быть пустым, пока пациент не нажмет /start
    tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    
    name: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Медицинские данные
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mobility: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Например: "Лежу", "Хожу"
    
    # План реабилитации (можно вынести в отдельную таблицу, если он сложный)
    rehab_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Обратные связи
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="patients")
    
    # Связи с логами и напоминаниями пациента
    reminders: Mapped[List["UserReminder"]] = relationship("UserReminder", back_populates="patient", cascade="all, delete-orphan")
    pain_logs: Mapped[List["PainLog"]] = relationship("PainLog", back_populates="patient", cascade="all, delete-orphan")
    meal_logs: Mapped[List["MealLog"]] = relationship("MealLog", back_populates="patient", cascade="all, delete-orphan")
    workout_logs: Mapped[List["WorkoutLog"]] = relationship("WorkoutLog", back_populates="patient", cascade="all, delete-orphan")


# --- Модели для логов и напоминаний (Новые) ---

class UserReminder(Base):
    __tablename__ = "user_reminders"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reminder_time: Mapped[time] = mapped_column(Time, nullable=False) # Хранится в формате ЧЧ:ММ
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    patient: Mapped["Patient"] = relationship("Patient", back_populates="reminders")


class PainLog(Base):
    __tablename__ = "pain_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    pain_level: Mapped[int] = mapped_column(Integer, nullable=False) # 0-10
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    patient: Mapped["Patient"] = relationship("Patient", back_populates="pain_logs")


class MealLog(Base):
    __tablename__ = "meal_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # КБЖУ может быть не распознано идеально, поэтому nullable=True
    calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proteins: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fats: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    patient: Mapped["Patient"] = relationship("Patient", back_populates="meal_logs")


class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False) # От 1 до 5 (тяжесть нагрузки)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    patient: Mapped["Patient"] = relationship("Patient", back_populates="workout_logs")