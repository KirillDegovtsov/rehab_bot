import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import time

class NotificationService:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone='Europe/Moscow')

    def start(self):
        self.scheduler.start()
        
    async def _send_reminder(self, chat_id: int, text: str):
        try:
            await self.bot.send_message(chat_id, f"🔔 Напоминание:\n{text}")
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления {chat_id}: {e}")

    def schedule_user_reminder(self, reminder_id: int, chat_id: int, text: str, reminder_time: time):
        job_id = f"reminder_{reminder_id}"
        self.scheduler.add_job(
            self._send_reminder,
            'cron',
            hour=reminder_time.hour,
            minute=reminder_time.minute,
            id=job_id,
            args=[chat_id, text],
            replace_existing=True
        )

    def remove_reminder(self, reminder_id: int):
        job_id = f"reminder_{reminder_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)