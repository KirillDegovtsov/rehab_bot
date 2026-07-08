import aiohttp
import json
import uuid
import logging
from config import config

class GigaChatService:
    def __init__(self):
        self.auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self.token = None
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def _update_token(self):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'RqUID': str(uuid.uuid4()),
            'Authorization': f'Basic {config.GIGACHAT_CREDENTIALS}'
        }
        
        connector = aiohttp.TCPConnector(verify_ssl=False)
        async with aiohttp.ClientSession(connector=connector, timeout=self.timeout) as session:
            try:
                async with session.post(self.auth_url, headers=headers, data='scope=GIGACHAT_API_PERS') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.token = data.get('access_token')
                        logging.info("GigaChat token successfully updated.")
                    else:
                        error_text = await resp.text()
                        logging.error(f"GigaChat Auth Error: {error_text}")
                        raise Exception(f"Ошибка авторизации GigaChat (Код {resp.status})")
            except Exception as e:
                logging.error(f"GigaChat Connection Error: {e}")
                raise Exception(f"Нет связи с GigaChat: {e}")

    async def generate_draft_plan(self, patient_data: dict) -> dict:
        if not self.token:
            await self._update_token()

        prompt = (
            f"Создай черновой план реабилитации для пациента.\n"
            f"Пациент: {patient_data}\n"
            f"Требование: Ответь СТРОГО в формате JSON без markdown и прочего текста.\n"
            f"Структура JSON: {{\"exercises\": [{{\"name\": \"название\", \"description\": \"как делать\", \"sets\": 3, \"reps\": 10}}], \"nutrition\": {{\"description\": \"общее описание диеты\", \"meals\": {{\"breakfast\": \"...\", \"lunch\": \"...\"}}}}}}"
        )

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        
        payload = {
            "model": "GigaChat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5
        }

        connector = aiohttp.TCPConnector(verify_ssl=False)
        async with aiohttp.ClientSession(connector=connector, timeout=self.timeout) as session:
            try:
                async with session.post(self.chat_url, headers=headers, json=payload) as resp:
                    if resp.status == 401:
                        await self._update_token()
                        return await self.generate_draft_plan(patient_data)
                    
                    if resp.status != 200:
                        error_text = await resp.text()
                        logging.error(f"GigaChat API Error: {error_text}")
                        raise Exception(f"Ошибка API (Код {resp.status})")

                    result = await resp.json()
                    content = result['choices'][0]['message']['content']
                    
                    try:
                        clean_json = content.replace("```json", "").replace("```", "").strip()
                        return json.loads(clean_json)
                    except json.JSONDecodeError:
                        logging.error(f"GigaChat Parsing Error. Raw content: {content}")
                        return {"exercises": [{"name": "Ошибка", "description": "Сбой парсинга ИИ", "sets": "-", "reps": "-"}], "nutrition": {"description": content}}
            except Exception as e:
                logging.error(f"GigaChat Generation Error: {e}")
                raise Exception(f"Ошибка генерации: {e}")

gigachat_client = GigaChatService()