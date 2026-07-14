# utils/filters.py

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery


class RoleFilter(Filter):
    """
    Фильтр роли. Использует значение 'role', которое кладёт в data middleware AuthMiddleware.
    Применяется на уровне роутера: router.message.filter(RoleFilter("admin"))
    """

    def __init__(self, role: str):
        self.role = role

    async def __call__(self, event: Message | CallbackQuery, **data) -> bool:
        # 'role' кладётся в data словарь middleware'ем AuthMiddleware
        current_role: str | None = data.get("role")
        return current_role == self.role