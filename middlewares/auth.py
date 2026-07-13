from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from database import async_session_maker
from database.crud import get_user_role

class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data: dict):
        user = event.from_user
        if not user:
            return await handler(event, data)
            
        if not user.username:
            msg = "⚠️ Для работы с ботом необходимо установить username в Telegram (в настройках профиля)."
            if isinstance(event, Message):
                await event.answer(msg)
            elif isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)
            return
            
        # Нормализация username
        username = user.username.lower().replace('@', '')
        
        async with async_session_maker() as session:
            role = await get_user_role(session, username)
            
        if not role:
            msg = "🚫 Вы не зарегистрированы в системе. Обратитесь к администратору или лечащему врачу."
            if isinstance(event, Message):
                await event.answer(msg)
            elif isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)
            return
            
        data['role'] = role
        data['username'] = username
        
        return await handler(event, data)