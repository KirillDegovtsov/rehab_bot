from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, Integer, ForeignKey, JSON


class Base(DeclarativeBase):
    pass


class Doctor(Base):
    __tablename__ = 'doctors'
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    fio: Mapped[str] = mapped_column(String)

    patients: Mapped[list["Patient"]] = relationship(back_populates="doctor")


class Patient(Base):
    __tablename__ = 'patients'
    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey('doctors.id'))

    name: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String, nullable=True)
    age: Mapped[int] = mapped_column(Integer)
    diagnosis: Mapped[str] = mapped_column(String)
    surgery_date: Mapped[str] = mapped_column(String)
    fracture_type: Mapped[str] = mapped_column(String, nullable=True)
    surgery_method: Mapped[str] = mapped_column(String, nullable=True)
    comorbidities: Mapped[str] = mapped_column(String, nullable=True)
    health_status: Mapped[str] = mapped_column(String, nullable=True)

    doctor: Mapped["Doctor"] = relationship(back_populates="patients")
    rehab_plan: Mapped["RehabPlan"] = relationship(
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan"
    )


class RehabPlan(Base):
    __tablename__ = 'rehab_plans'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey('patients.id'), unique=True)
    exercises_json: Mapped[dict] = mapped_column(JSON)
    nutrition_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default='draft')

    patient: Mapped["Patient"] = relationship(back_populates="rehab_plan")