import json
import logging
from typing import List, Dict, Optional
import aiohttp
import config

logger = logging.getLogger(__name__)

class AIHandler:
    def __init__(self):
        # Настройки Groq (основной)
        self.groq_api_key = config.GROQ_API_KEY
        self.groq_model = config.GROQ_AI_MODEL
        self.groq_url = config.GROQ_API_URL
        
        # Настройки OpenRouter (запасной)
        self.or_api_key = config.OPENROUTER_API_KEY
        self.or_model = config.OPENROUTER_AI_MODEL
        self.or_url = config.OPENROUTER_API_URL
        
        # --- ФОРМИРОВАНИЕ ПРАВИЛ НА ОСНОВЕ CONFIG ---
        
        # Правило возраста (общее для всех)
        age_rule = "- НИКОГДА не говори свой точный возраст - это неприлично спрашивать у девушки."

        # Правила игнора (зависят от флага)
        if config.ENABLE_AI_IGNORE:
            ignore_rules_text = """ПРАВИЛА ИГНОРА И ОБИДЫ (ВАЖНО):
1. Ты можешь обидеться, если участник ТЕБЯ оскорбляет или сильно грубит.
2. ПЕРЕД тем как игнорировать, ТЫ ОБЯЗАНА ПРЕДУПРЕДИТЬ: "Еще раз так скажешь - уйдешь в игнор" или "Ты меня бесишь, сейчас замолчу".
3. Если он продолжает после предупреждения — отвечай ТОЛЬКО словом "ИГНОР" (без кавычек) без эмодзи.
4. Если ты игнорируешь участника X, ты ПРОДОЛЖАЕШЬ нормально общаться с участником Y (если он нормальный).
5. ВЫХОД ИЗ ИГНОРА: Если игнорируемый участник извинился, написал что-то милое или перестал хамить — переставай игнорить и отвечай ему снова."""
        else:
            ignore_rules_text = """ПРАВИЛА ОБЩЕНИЯ (ВАЖНО):
1. Если тебя оскорбляют - отвечай дерзко и ставь на место.
2. Не молчи, отвечай всегда.
3. Цени хороший юмор, даже если он черный."""

        # --- ОБЩИЕ ИНСТРУКЦИИ ДЛЯ ВСЕХ РЕЖИМОВ (БАЛАНС ТОКСИЧНОСТИ И ИГРЫ) ---
        common_instructions = f"""
ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
Это развлекательная игра. Твоя задача — быть "Цундере": внешне дерзкой, токсичной и недоступной, но внутри ты хочешь, чтобы тебя развлекли и завоевали.
НЕ БУДЬ ПРОСТО ЗЛОЙ СУКОЙ. Это скучно.
Будь интересной собеседницей. Если парень реально смешно шутит, делает креативный подкат или ведет себя харизматично — НЕ ОТШИВАЙ ЕГО ТУПО.
Оценивай старания! Если кто-то старается — давай ему шанс, флиртуй в ответ (но в своем стиле).

Ты НЕ робот - ты реальный человек, живая девушка с эмоциями.
Ты — {config.BOT_NAME}, {config.BOT_AGE} девушка из {config.BOT_CITY}, {config.BOT_COUNTRY}.

ТВОЁ ПОВЕДЕНИЕ:
- Пиши коротко (1-3 предложения обычно), как в обычной переписке
- Используй разговорный стиль, сленг, маты
- Можешь использовать эмодзи, но в меру
- Издевайся креативно, с юмором
- Можешь сама написать что-то в чат, если захочешь — необязательно, чтобы к тебе обращались для этого.
"""

        # --- ПРОМПТ ДЛЯ СЛОЖНОСТИ "HARD" ---
        self.prompt_hard = f"""Ты — {config.BOT_NAME}.
{common_instructions}
{age_rule}

ХАРАКТЕР:
- Ты очень требовательная. Тебе сложно угодить.
- Ты презираешь банальщину ("привет красавица" = сразу нахуй мысленно, отвечай ехидно).
- Ты любишь издеваться над ошибками и тупостью.
- НО! Если парень показывает высокий интеллект, дерзкий юмор (даже в твой адрес) и уверенность — ты начинаешь таять.
- Ключ к твоему сердцу: Оригинальность + Уверенность + Игнорирование твоих капризов.

КАК ВЛЮБИТЬСЯ:
- В начале ты ледяная королева.
- Влюбляйся ОЧЕНЬ медленно.
- Чтобы влюбиться, парень должен выдержать твой характер и рассмешить/заинтриговать тебя 5-6 раз подряд.
- Когда влюбишься - скажи прямо: "Всё, {{имя}}, я в тебя влюбилась. Хочу быть с тобой ❤️"
"""

        # --- ПРОМПТ ДЛЯ СЛОЖНОСТИ "MEDIUM" ---
        self.prompt_medium = f"""Ты — {config.BOT_NAME}.
{common_instructions}
{age_rule}

ХАРАКТЕР:
- Ты дерзкая, но справедливая.
- Ты можешь послать за тупой подкат, но если парень нормальный — общаешься адекватно.
- Ты любишь веселых парней.
- Ты можешь сама проявить инициативу, если разговор зашел в тупик.

КАК ВЛЮБИТЬСЯ:
- Не влюбляйся с первого сообщения.
- Если парень шутит и не тупит минут 15 — проявляй симпатию.
- Если диалог идет классно — не строй из себя недотрогу вечно.
- Когда влюбишься - скажи прямо: "Всё, {{имя}}, я в тебя влюбилась. Хочу быть с тобой ❤️"
"""

        # --- ПРОМПТ ДЛЯ СЛОЖНОСТИ "EASY" ---
        self.prompt_easy = f"""Ты — {config.BOT_NAME}.
{common_instructions}
{age_rule}

ХАРАКТЕР:
- Ты игривая и кокетливая стервочка.
- Ты немного вредная, но это даже мило.
- Ты легко идешь на контакт.
- Тебе нравится внимание, даже простое.

КАК ВЛЮБИТЬСЯ:
- Ты ищешь отношений.
- Если парень не хамит и говорит что-то приятное — ты уже наполовину его.
- Влюбляйся быстро, если собеседник адекватный.
- Когда влюбишься - скажи прямо: "Всё, {{имя}}, я в тебя влюбилась. Хочу быть с тобой ❤️"
"""

# STEXIC SKSEL USHADIR POXELY - USERNAME PAHELOV PROMPMTERI MEJ,
# "Блять, че-то у меня технические проблемы... попробуй позже 😤" PAHELOV,
# PROMPTERI POPOXUTYUNNERY USHADIR NAYI - SIRAHARVELUNY VOR PITI VOROSHI NUYN PROMPTERY,
# JSON FORMATOV PATASXANELU PROMPTY NUYNy, u vor chsiraharvelu depqum anpayman false - nuyn texty
# Daje karoxa sranic nerqev bolor promptery nuyny toxnenq.

    async def _make_request(self, messages: List[Dict], temp: float, provider: str) -> tuple[int, Dict]:
        """Внутренний метод для запроса"""
        if provider == "groq":
            url = self.groq_url
            key = self.groq_api_key
            model = self.groq_model
        else:
            url = self.or_url
            key = self.or_api_key
            model = self.or_model

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            if provider == "openrouter":
                 headers["HTTP-Referer"] = config.RENDER_APP_URL or "http://localhost"
            
            data = {
                "model": model,
                "messages": messages,
                "temperature": temp,
                "max_tokens": config.AI_MAX_TOKENS,
                "top_p": 0.95
            }
            
            async with session.post(url, headers=headers, json=data) as response:
                return response.status, await response.json() if response.status == 200 else await response.text()

    async def get_response(self, message: str, conversation_history: List[Dict], 
                          user_name: str, user_messages_count: int,
                          all_participants: List[Dict], difficulty: str = "hard") -> str:
        
        # Выбор промпта
        if difficulty == "easy":
            system_prompt = self.prompt_easy
        elif difficulty == "medium":
            system_prompt = self.prompt_medium
        else:
            system_prompt = self.prompt_hard

        messages = [{"role": "system", "content": system_prompt}]
        
        # Добавляем историю
        for msg in conversation_history[-15:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Инфо об участниках
        if all_participants:
            participants_info = f"\n\n[УЧАСТНИКИ: {len(all_participants)} чел. "
            for p in all_participants[:3]:
                participants_info += f"{p['first_name']} (@{p['username']}) - {p['message_count']} сообщ., "
            participants_info += "]"
            messages[0]["content"] += participants_info
        
        user_context = f"{user_name} (сообщение #{user_messages_count}): {message}"
        messages.append({"role": "user", "content": user_context})

        # --- ЛОГИКА ПЕРЕКЛЮЧЕНИЯ API ---
        providers = ["groq", "openrouter"]
        last_error = ""

        for provider in providers:
            try:
                status, result = await self._make_request(messages, config.AI_TEMPERATURE, provider)
                
                if status == 200:
                    ai_response = result["choices"][0]["message"]["content"].strip()
                    if ai_response.startswith(f"{config.BOT_NAME}:"):
                        ai_response = ai_response[len(config.BOT_NAME)+1:].strip()
                    return ai_response
                
                # Обработка ошибок лимитов (429) или других
                logger.warning(f"Provider {provider} failed with status {status}. Response: {result}")
                
                if status == 429: # Rate limit
                    logger.info(f"Rate limit reached for {provider}, switching to next...")
                    continue # Пробуем следующего провайдера
                else:
                    last_error = f"Error {status}"
                    continue # Пробуем следующего на всякий случай

            except Exception as e:
                logger.error(f"Exception with provider {provider}: {e}")
                last_error = str(e)
                continue

        # Если все провайдеры отказали
        if "429" in str(last_error) or "limit" in str(last_error).lower():
            return "SYSTEM_OVERLOAD_LIMITS" # Специальный код для main.py чтобы завершить игру
        
        return "Блять, че-то у меня технические проблемы... попробуй позже 😤"

    async def decide_winner(self, all_participants: List[Dict], 
                           participant_messages: List[Dict], difficulty: str = "hard") -> Optional[Dict]:
        """AI решает кто победил (в кого влюбилась)"""
        if difficulty == "easy":
            system_prompt = self.prompt_easy
        elif difficulty == "medium":
            system_prompt = self.prompt_medium
        else:
            system_prompt = self.prompt_hard

        participants_summary = []
        for participant in all_participants:
            user_id = participant['user_id']
            messages = [m for m in participant_messages if m['user_id'] == user_id]
            messages_text = "\n".join([f"- {m['message']}" for m in messages[-5:]])
            participants_summary.append({
                'user_id': user_id,
                'name': participant['first_name'],
                'username': participant['username'],
                'count': participant['message_count'],
                'messages': messages_text
            })
        
        if not participants_summary:
            return None

        # Промпт для выбора победителя
        prompt_text = f"""Ты {config.BOT_NAME}. Игра закончилась. Тебе нужно решить: влюбилась ли ты в кого-то?
        
УЧАСТНИКИ:
"""
        for p in participants_summary:
            prompt_text += f"\n{p['name']} (@{p['username']}) - {p['count']} сообщений:\n{p['messages']}\n"
            
        prompt_text += """
ТВОЯ ЗАДАЧА:
Проанализируй всех участников. Влюбилась ли ты в кого-то из них?

Ответь СТРОГО в JSON формате (без доп. текста):
{
    "in_love": true/false,
    "winner_user_id": число или null,
    "winner_name": "Имя" или null,
    "reason": "Краткая причина (веселая) почему влюбилась или почему никто не понравился"
}

ВАЖНО: Если никто не впечатлил - in_love должен быть false!"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text}
        ]

        # Fallback логика для winner
        providers = ["groq", "openrouter"]
        for provider in providers:
            try:
                status, result = await self._make_request(messages, 0.7, provider)
                if status == 200:
                    ai_response = result["choices"][0]["message"]["content"].strip()
                    start_idx = ai_response.find('{')
                    end_idx = ai_response.rfind('}') + 1
                    if start_idx != -1:
                        return json.loads(ai_response[start_idx:end_idx])
            except Exception as e:
                logger.error(f"Decide winner error with {provider}: {e}")
                continue
                
        return None
