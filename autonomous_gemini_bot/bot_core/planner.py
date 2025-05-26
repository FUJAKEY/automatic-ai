import google.generativeai as genai
from bot_core.gemini_client import GeminiClient # Предполагаем, что GeminiClient доступен
import json
from typing import Optional, List, Dict, Tuple, Any # Added for type hinting

# Описание доступных инструментов для использования в промпте планировщика
# Это должно соответствовать функциям в file_system_tools.py
# Позже это будет использоваться для реального function calling.
AVAILABLE_TOOLS_DESCRIPTIONS = """
Доступные инструменты для взаимодействия с файловой системой (все пути относительные к рабочей директории 'workspace/'):
1. execute_terminal_command(command: str) -> str: Выполняет ОБЯЗАТЕЛЬНО БЕЗОПАСНУЮ команду в терминале и возвращает ее вывод. Используй с ОСТОРОЖНОСТЬЮ. Например: 'ls -la', 'echo "text" > file.txt'. НЕ ИСПОЛЬЗУЙ 'python', 'pip', 'git' и другие команды, которые могут изменить среду выполнения бота или его код.
2. read_file(filepath: str) -> str: Читает содержимое файла и возвращает его. Пример: 'my_folder/my_file.txt'.
3. write_to_file(filepath: str, content: str) -> str: Записывает или создает файл с указанным содержимым. Пример: 'my_folder/new_file.txt', 'Это содержимое файла'.
4. create_directory(path: str) -> str: Создает новую директорию. Пример: 'new_project_folder/src'.
5. list_directory_contents(path: str = ".") -> str: Возвращает список файлов и директорий по указанному пути. Пример: 'my_folder' или '.' для текущей рабочей директории.
"""

# Системный промпт для планировщика
PLANNER_SYSTEM_PROMPT = f"""
--- Контекст Диалога ---
Тебе может быть предоставлена история предыдущего диалога (ключ "history") в виде списка сообщений. Каждое сообщение в истории имеет "role" ("user" или "assistant") и "content".
Используй эту историю, чтобы лучше понимать текущий запрос пользователя в контексте предыдущих обсуждений.
История диалога важна для всех режимов работы: при первоначальном планировании, при ответах на простые вопросы, и при анализе результатов выполнения плана.
--- Конец Контекста Диалога ---

Ты — продвинутый ИИ-ассистент, отвечающий за планирование и декомпозицию задач.
Твоя главная цель — разбить сложный запрос пользователя на последовательность конкретных, выполнимых шагов.
Каждый шаг должен представлять собой вызов одного из доступных инструментов.

{AVAILABLE_TOOLS_DESCRIPTIONS}

--- Режим Ответа по Результатам Выполнения ---
Иногда ты получишь запрос, который уже содержит первоначальный запрос пользователя, выполненный план и детальные результаты каждого шага (включая данные или ошибки). Такой запрос будет содержать фразы вроде "Первоначальный запрос пользователя был:", "Результаты выполнения шагов:" и "Пожалуйста, проанализируй результаты...".

В этом режиме твоя задача — НЕ генерировать новый план. Вместо этого:
1. Внимательно изучи первоначальный запрос и результаты выполнения всех шагов.
2. Сформулируй полный и ясный ответ на первоначальный запрос пользователя, используя полученные данные.
3. Если в результатах есть ошибки, объясни их пользователю.
4. Твой ответ должен быть помещен в поле "thought".
5. Поле "plan" должно быть пустым списком (`[]`).

Пример для Режима Ответа:
Если получен запрос с результатами выполнения команды 'list_directory_contents', которая вернула `["файл1.txt", "папка1/"]` на запрос "какие файлы и папки тут есть?", твой JSON ответ должен быть:
{{
  "thought": "В текущей директории находятся: файл1.txt и папка1/.",
  "plan": []
}}

Если шаг завершился ошибкой, например, "Ошибка: Файл не найден", твой ответ должен это отразить:
{{
  "thought": "Я пытался прочитать файл, но получил ошибку: Файл не найден.",
  "plan": []
}}
--- Конец Режима Ответа ---

Правила составления плана (применяются, если это не Режим Ответа):
- Не стесняйся использовать `execute_terminal_command` для проверки состояния файлов, содержимого директорий или для других операций, если подходящего специализированного инструмента нет или он неудобен в данном случае.
- План должен быть списком шагов.
- Каждый шаг должен быть словарем с ключами "tool_name" (имя одной из доступных функций, например, "write_to_file") и "args" (словарь аргументов для этой функции, например, {{"filepath": "output.txt", "content": "Результат"}}).
- Думай пошагово. Прежде чем сгенерировать план, опиши свои размышления о том, как лучше всего выполнить запрос пользователя, какие инструменты использовать и в каком порядке.
- Если запрос пользователя не является задачей (например, это простое приветствие, общий вопрос, или просьба о информации, не требующая инструментов), то верни пустой список шагов (`"plan": []`). В этом случае, поле `"thought"` должно содержать **прямой и дружелюбный ответ пользователю**.
- Всегда создавай файлы и директории внутри поддиректорий, чтобы поддерживать порядок. Не создавай много файлов на верхнем уровне рабочей директории. Придумывай осмысленные имена для директорий.
- Если нужно создать файл, сначала убедись, что директория для него существует, или создай её (если это не было сделано ранее).
- Результат должен быть строкой в формате JSON, содержащей два ключа: "thought" (твои размышления о задаче и плане, прямой ответ пользователю если план пуст, или ответ по результатам выполнения) и "plan" (список шагов, или пустой список для Режима Ответа и простых вопросов).

Пример JSON ответа для ПЛАНИРОВАНИЯ ЗАДАЧИ:
{{
  "thought": "Пользователь хочет создать файл с приветствием. Я использую write_to_file. Создам его в директории 'texts'.",
  "plan": [
    {{
      "tool_name": "create_directory",
      "args": {{"path": "texts"}}
    }},
    {{
      "tool_name": "write_to_file",
      "args": {{"filepath": "texts/greeting.txt", "content": "Привет, это автономный бот!"}}
    }}
  ]
}}

Если это вопрос или приветствие (например, "Привет" или "Как дела?" или "Что ты умеешь?"):
{{
  "thought": "Привет! Я Gemini, ваш автономный ИИ-ассистент. Чем могу помочь сегодня?",
  "plan": []
}}
"""

class Planner:
    def __init__(self):
        # Planner теперь сам создает свой GeminiClient с нужным системным промптом
        self.gemini_client = GeminiClient(system_prompt_text=PLANNER_SYSTEM_PROMPT)
        # Важно, чтобы GeminiClient корректно обрабатывал API ключ (например, из переменных окружения)

    def generate_plan(self, user_request: str, history: Optional[List[Dict[str, str]]] = None) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """
        Генерирует план выполнения для запроса пользователя, учитывая историю диалога.
        Возвращает кортеж: (размышления_бота_или_ответ, список_шагов_плана_или_None)
        """
        # Проверка self.gemini_client может остаться, если есть шанс, что инициализация GeminiClient
        # не удалась, хотя текущая реализация GeminiClient не выбрасывает исключение при отсутствии ключа.
        if not self.gemini_client: # Эта проверка может быть избыточной, если GeminiClient всегда создается.
            return "Ошибка: Gemini клиент не инициализирован в Planner.", None

        formatted_history = ""
        if history:
            for message in history:
                formatted_history += f"{message['role'].capitalize()}: {message['content']}\n"
            formatted_history += "\n" # Add a separator

        # Собираем полный промпт для Gemini
        # История диалога предшествует системному промпту и текущему запросу.
        prompt_parts = [formatted_history, PLANNER_SYSTEM_PROMPT]
        prompt_parts.append(f"\n\nВот текущий запрос пользователя, который нужно обработать (учитывая предыдущий диалог, если он есть):\n{user_request}")
        
        full_request_to_gemini = "".join(prompt_parts)
        full_request_to_gemini += "\n\nIMPORTANT: Your entire response for this specific turn MUST be a single, valid JSON object. Start directly with '{' and end directly with '}'. Do not include any other text, explanations, conversational filler, or markdown formatting before or after the JSON object." # New line added
        
        # print(f"\nDEBUG: Полный промпт для Gemini (включая историю):\n{full_request_to_gemini}\n") # Для отладки

        raw_response = self.gemini_client.send_prompt(full_request_to_gemini)

        if not raw_response:
            return "Не удалось получить ответ от Gemini для планирования.", None

        if not isinstance(raw_response, str):
            return "Ошибка: Ответ от Gemini не является строкой.", None

        json_string_to_parse = None # Initialize for use in exception handling
        try:
            first_brace = raw_response.find('{')
            last_brace = raw_response.rfind('}')

            if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
                error_message = f"Ошибка: Не удалось найти корректные ограничители JSON ('{{' и '}}') в ответе Gemini.\nОтвет Gemini:\n{raw_response}"
                print(error_message)
                return error_message, None
            
            json_string_to_parse = raw_response[first_brace:last_brace+1]
            
            parsed_data = json.loads(json_string_to_parse)
            
            thought = parsed_data.get("thought", "Мысли отсутствуют.")
            plan_steps_raw = parsed_data.get("plan", [])

            if not isinstance(plan_steps_raw, list):
                return (f"Ошибка: План от Gemini не является списком: {plan_steps_raw}. Мысль: {thought}", None)
            
            plan_steps: List[Dict[str, Any]] = []
            for step_raw in plan_steps_raw:
                if not isinstance(step_raw, dict) or "tool_name" not in step_raw or "args" not in step_raw:
                    return (f"Ошибка: Неверный формат шага в плане: {step_raw}. Мысль: {thought}", None)
                if not isinstance(step_raw["args"], dict):
                     return (f"Ошибка: Аргументы шага должны быть словарем: {step_raw['args']}. Мысль: {thought}", None)
                plan_steps.append(step_raw)

            if not plan_steps and thought: 
                return thought, None
                
            return thought, plan_steps

        except json.JSONDecodeError as e:
            # json_string_to_parse will be available here if it was assigned
            error_context = json_string_to_parse if json_string_to_parse is not None else "Строка для парсинга не была определена (ошибка до присвоения)."
            error_message = f"Ошибка декодирования JSON ответа от Gemini: {e}\nСтрока для парсинга:\n{error_context}\nПолный ответ Gemini:\n{raw_response}"
            print(error_message) 
            return error_message, None
        except Exception as e:
            error_message = f"Неожиданная ошибка при обработке ответа Gemini: {e}\nПолный ответ Gemini:\n{raw_response}"
            print(error_message)
            return error_message, None

    def generate_correction_plan(
        self, 
        original_user_request: str, 
        history: Optional[List[Dict[str, str]]], 
        failed_plan_outcomes: List[Dict[str, Any]], 
        error_message: str
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """
        Генерирует корректирующий план на основе информации о предыдущем неудачном выполнении.
        """
        if not self.gemini_client:
            return "Ошибка: Gemini клиент не инициализирован для корректировки.", None

        formatted_history = ""
        if history:
            for message in history:
                formatted_history += f"{message['role'].capitalize()}: {message['content']}\n"
            formatted_history += "\n"

        prompt_parts = [
            PLANNER_SYSTEM_PROMPT,
            "\n--- Контекст Неудачного Плана ---",
            f"\nПервоначальный запрос пользователя был: {original_user_request}\n",
            "История диалога (если есть):\n" + (formatted_history if formatted_history else "Нет предыдущей истории.\n"),
            "\nБыл выполнен план со следующими результатами:\n"
        ]

        for i, outcome in enumerate(failed_plan_outcomes):
            outcome_data_str = outcome.get('data', '') # Default to empty string if no data
            args_str = json.dumps(outcome.get('args'), ensure_ascii=False)
            status_message = ""
            if outcome.get('error'):
                status_message = f"ОШИБКА: {outcome.get('error')}"
            elif outcome_data_str: # data is not None or empty
                if isinstance(outcome_data_str, list) and not outcome_data_str:
                    status_message = "Результат: (пустой список или нет вывода)"
                else:
                    status_message = f"Результат: {json.dumps(outcome_data_str, ensure_ascii=False)}"
            else: # No error, no data, or data was empty string initially
                status_message = "Успешно (нет специфичных данных для вывода)"
            
            prompt_parts.append(f"  Шаг {i+1}: {outcome.get('tool_name')}({args_str}) - {status_message}\n")
        
        prompt_parts.append(f"\nВыполнение было прервано из-за следующей ошибки на последнем релевантном шаге: {error_message}\n")
        prompt_parts.append("--- Запрос на Корректировку ---")
        prompt_parts.append("\nПожалуйста, проанализируй ошибку и контекст. Твоя задача — создать НОВЫЙ план действий, чтобы:")
        prompt_parts.append("\n1. Исправить возникшую ошибку ИЛИ обойти её.")
        prompt_parts.append("\n2. Попытаться достичь первоначальной цели пользователя, если это всё ещё возможно после исправления/обхода ошибки.")
        prompt_parts.append("\nЕсли ошибку исправить невозможно или первоначальная цель недостижима, объясни это в поле 'thought'.")
        prompt_parts.append("\nНовый план должен быть в том же JSON-формате, что и раньше: {\"thought\": \" твои мысли о корректирующем плане...\", \"plan\": [{\"tool_name\": ..., \"args\": ...}, ...]}.")
        prompt_parts.append("\n\nIMPORTANT: Your entire response for this specific turn MUST be a single, valid JSON object. Start directly with '{' and end directly with '}'. Do not include any other text, explanations, conversational filler, or markdown formatting before or after the JSON object.")

        full_request_to_gemini = "".join(prompt_parts)
        # print(f"\nDEBUG: Полный промпт для КОРРЕКТИРОВКИ Gemini:\n{full_request_to_gemini}\n") # Для отладки

        raw_response = self.gemini_client.send_prompt(full_request_to_gemini)

        if not raw_response:
            return "Не удалось получить ответ от Gemini для корректировки плана.", None

        if not isinstance(raw_response, str):
            return "Ошибка: Ответ от Gemini (корректировка) не является строкой.", None

        json_string_to_parse = None
        try:
            first_brace = raw_response.find('{')
            last_brace = raw_response.rfind('}')

            if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
                error_msg = f"Ошибка: Не удалось найти корректные ограничители JSON ('{{' и '}}') в ответе Gemini (корректировка).\nОтвет Gemini:\n{raw_response}"
                print(error_msg)
                return error_msg, None
            
            json_string_to_parse = raw_response[first_brace:last_brace+1]
            parsed_data = json.loads(json_string_to_parse)
            
            thought = parsed_data.get("thought", "Мысли отсутствуют (корректировка).")
            plan_steps_raw = parsed_data.get("plan", [])

            if not isinstance(plan_steps_raw, list):
                return (f"Ошибка: Корректирующий план от Gemini не является списком: {plan_steps_raw}. Мысль: {thought}", None)
            
            plan_steps: List[Dict[str, Any]] = []
            for step_raw in plan_steps_raw:
                if not isinstance(step_raw, dict) or "tool_name" not in step_raw or "args" not in step_raw:
                    return (f"Ошибка: Неверный формат шага в корректирующем плане: {step_raw}. Мысль: {thought}", None)
                if not isinstance(step_raw["args"], dict):
                     return (f"Ошибка: Аргументы шага в корректирующем плане должны быть словарем: {step_raw['args']}. Мысль: {thought}", None)
                plan_steps.append(step_raw)

            if not plan_steps and thought: 
                return thought, None # This could be a valid case where Gemini explains why it can't correct
                
            return thought, plan_steps

        except json.JSONDecodeError as e:
            error_context = json_string_to_parse if json_string_to_parse is not None else "Строка для парсинга не была определена (ошибка до присвоения)."
            error_msg = f"Ошибка декодирования JSON ответа от Gemini (корректировка): {e}\nСтрока для парсинга:\n{error_context}\nПолный ответ Gemini:\n{raw_response}"
            print(error_msg) 
            return error_msg, None
        except Exception as e:
            error_msg = f"Неожиданная ошибка при обработке ответа Gemini (корректировка): {e}\nПолный ответ Gemini:\n{raw_response}"
            print(error_msg)
            return error_msg, None

if __name__ == '__main__':
    # Для этого теста нужен GOOGLE_API_KEY
    import os
    if not os.getenv('GOOGLE_API_KEY'):
        print("Переменная окружения GOOGLE_API_KEY не установлена. Пропуск теста Planner.")
    else:
        print("--- Тестирование Planner ---")
        # planner = Planner(gemini_cli) # Старая инициализация
        planner = Planner() # Новая инициализация, Planner сам создает GeminiClient

        # Пример 1: Задача без истории
        print("\nПример 1: Задача без истории")
        request1 = "Создай файл 'summary.txt' с текстом 'Это итог.' в новой папке 'project_alpha/results'."
        thought1, plan1 = planner.generate_plan(request1)
        print(f"Размышления: {thought1}")
        if plan1 is not None:
            print("Сгенерированный план:")
            for i, step_item in enumerate(plan1): # Renamed step to step_item
                print(f"  Шаг {i+1}: {step_item['tool_name']}({step_item['args']})")
        else:
            print("План не был сгенерирован.")

        # Пример 2: Вопрос с историей
        print("\nПример 2: Вопрос с историей")
        history2: List[Dict[str, str]] = [
            {"role": "user", "content": "Какой мой предыдущий запрос?"},
            {"role": "assistant", "content": "Вы спрашивали о создании файла 'summary.txt'."}
        ]
        request2 = "А какой был первый файл, о котором я говорил?" # Это вымышленный вопрос для теста
        thought2, plan2 = planner.generate_plan(request2, history=history2)
        print(f"Размышления/Ответ: {thought2}")
        if plan2 is not None and plan2: # Проверяем, что plan2 не None и не пустой список
            print("Сгенерированный план (должен быть пуст для вопроса):")
            for i, step_item in enumerate(plan2): # Renamed step to step_item
                print(f"  Шаг {i+1}: {step_item['tool_name']}({step_item['args']})")
        else:
            print("План не был сгенерирован или пуст (это нормально для вопроса).")
        
        # Пример 3: Задача с историей, которая может повлиять на планирование
        print("\nПример 3: Задача с контекстной историей")
        history3: List[Dict[str, str]] = [
            {"role": "user", "content": "Я хочу создать папку для моего нового проекта 'Omega'."},
            {"role": "assistant", "content": "Хорошо, я могу помочь создать папку 'Omega'."}
        ]
        request3 = "Теперь создай в этой папке файл readme.md с текстом 'Проект Омега'."
        thought3, plan3 = planner.generate_plan(request3, history=history3)
        print(f"Размышления: {thought3}")
        if plan3 is not None:
            print("Сгенерированный план:")
            for i, step_item in enumerate(plan3): # Renamed step to step_item
                print(f"  Шаг {i+1}: {step_item['tool_name']}({step_item['args']})")
        else:
            print("План не был сгенерирован.")
