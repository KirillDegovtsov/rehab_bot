from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery

class RoleFilter(Filter):
    def __init__(self, role: str):
        self.role = role

    async def __call__(self, event, role: str) -> bool:
        return role == self.role