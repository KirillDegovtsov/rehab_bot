from .doctor import router as doctor_router
from .patient import router as patient_router

__all__ = ["doctor_router", "patient_router"]