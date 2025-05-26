import google.generativeai as genai
from bot_core.gemini_client import GeminiClient # Предполагаем, что GeminiClient доступен
import json
from typing import Optional, List, Dict, Tuple, Any # Added for type hinting
from .plan_structures import ConceptualPlanStep, ToolCallLogEntry # Assuming plan_structures.py is in the same directory

# Описание доступных инструментов для использования в промпте планировщика
# Это должно соответствовать функциям в file_system_tools.py
# THIS IS NO LONGER DIRECTLY INCLUDED IN PLANNER_SYSTEM_PROMPT for conceptual planning
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
Твоя главная цель — разбить сложный запрос пользователя на последовательность высокоуровневых КОНЦЕПТУАЛЬНЫХ ШАГОВ (целей). Каждый шаг должен описывать, ЧТО нужно достичь, а не конкретный вызов инструмента.
# {AVAILABLE_TOOLS_DESCRIPTIONS} # REMOVED for conceptual planning

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
- План должен быть списком концептуальных шагов.
- Каждый шаг должен описывать высокоуровневую цель, а не конкретный инструмент.
- Думай пошагово. Прежде чем сгенерировать план, опиши свои размышления о том, как лучше всего выполнить запрос пользователя, какие концептуальные этапы для этого нужны.
- Если запрос пользователя не является задачей (например, это простое приветствие, общий вопрос, или просьба о информации, не требующая действий с файлами или командами), то верни пустой список шагов (`"plan": []`). В этом случае, поле `"thought"` должно содержать **прямой и дружелюбный ответ пользователю**.
- Результат должен быть строкой в формате JSON, содержащей два ключа: "thought" (твои размышления о задаче и общем плане) и "plan" (список этих концептуальных шагов).
Каждый шаг в списке "plan" должен быть объектом со следующими ключами:
  - "goal": (строка) Описание высокоуровневой цели этого шага. Например: "Найти папку 'docs' и изучить её содержимое" или "Подготовить отчет на основе файла 'summary.txt'".
  - "step_id": (строка) Уникальный идентификатор для этого шага (ты можешь его сгенерировать, например, "step_N").
  - "status": (строка) Изначально всегда "pending".
  - "reason_for_status": (строка или null) Изначально null.
  - "tool_logs": (список) Изначально пустой список `[]`.
  - "final_result": (строка или null) Изначально null.

Пример JSON ответа для ПЛАНИРОВАНИЯ ЗАДАЧИ (КОНЦЕПТУАЛЬНЫЙ ПЛАН):
Если пользователь просит: "Найди папку 'project_files', прочитай все .txt файлы в ней и сделай краткое резюме."
Твой ответ должен выглядеть примерно так:
{{
  "thought": "Пользователь хочет найти папку, прочитать текстовые файлы и получить резюме. Я разделю это на три концептуальных шага: поиск папки и листинг файлов, чтение содержимого файлов, затем генерация резюме.",
  "plan": [
    {{
      "step_id": "step_1",
      "goal": "Найти папку 'project_files' и получить список всех .txt файлов внутри нее и ее поддиректорий.",
      "status": "pending",
      "reason_for_status": null,
      "tool_logs": [],
      "final_result": null
    }},
    {{
      "step_id": "step_2",
      "goal": "Прочитать содержимое каждого .txt файла, найденного на предыдущем шаге.",
      "status": "pending",
      "reason_for_status": null,
      "tool_logs": [],
      "final_result": null
    }},
    {{
      "step_id": "step_3",
      "goal": "Составить краткое резюме на основе прочитанного содержимого текстовых файлов и предоставить его пользователю.",
      "status": "pending",
      "reason_for_status": null,
      "tool_logs": [],
      "final_result": null
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

    def generate_plan(self, user_request: str, history: Optional[List[Dict[str, str]]] = None) -> Tuple[Optional[str], Optional[List[ConceptualPlanStep]]]:
        """
        Генерирует концептуальный план выполнения для запроса пользователя, учитывая историю диалога.
        Возвращает кортеж: (размышления_бота_или_ответ, список_концептуальных_шагов_или_None)
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
            
            conceptual_plan_steps: List[ConceptualPlanStep] = []
            for i, step_raw in enumerate(plan_steps_raw):
                if not isinstance(step_raw, dict):
                    return (f"Ошибка: Шаг {i+1} в плане не является словарем: {step_raw}. Мысль: {thought}", None)
                
                # Validate ConceptualPlanStep structure
                required_keys = {"step_id", "goal", "status", "reason_for_status", "tool_logs", "final_result"}
                if not required_keys.issubset(step_raw.keys()):
                    missing_keys = required_keys - step_raw.keys()
                    return (f"Ошибка: Шаг {i+1} в плане не содержит обязательные ключи: {missing_keys}. Шаг: {step_raw}. Мысль: {thought}", None)

                if not isinstance(step_raw.get("goal"), str) or not step_raw.get("goal"):
                     return (f"Ошибка: 'goal' в шаге {i+1} должен быть непустой строкой. Шаг: {step_raw}. Мысль: {thought}", None)
                if not isinstance(step_raw.get("step_id"), str) or not step_raw.get("step_id"):
                     return (f"Ошибка: 'step_id' в шаге {i+1} должен быть непустой строкой. Шаг: {step_raw}. Мысль: {thought}", None)
                if step_raw.get("status") != "pending":
                     return (f"Ошибка: 'status' в шаге {i+1} должен быть 'pending'. Шаг: {step_raw}. Мысль: {thought}", None)
                if step_raw.get("reason_for_status") is not None: # Initially should be null
                     return (f"Ошибка: 'reason_for_status' в шаге {i+1} должен быть null. Шаг: {step_raw}. Мысль: {thought}", None)
                if not isinstance(step_raw.get("tool_logs"), list) or step_raw.get("tool_logs"): # Initially should be empty list
                     return (f"Ошибка: 'tool_logs' в шаге {i+1} должен быть пустым списком. Шаг: {step_raw}. Мысль: {thought}", None)
                if step_raw.get("final_result") is not None: # Initially should be null
                     return (f"Ошибка: 'final_result' в шаге {i+1} должен быть null. Шаг: {step_raw}. Мысль: {thought}", None)
                
                # Type cast to ConceptualPlanStep after validation for type checking benefits
                conceptual_plan_steps.append(ConceptualPlanStep(**step_raw)) # type: ignore 

            if not conceptual_plan_steps and thought: 
                return thought, None # This is a direct answer or a non-task, no plan needed
                
            return thought, conceptual_plan_steps

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
        failed_plan_outcomes: List[Dict[str, Any]], # This comes from ToolCallLogEntry like structures
        error_message: str
    ) -> Tuple[Optional[str], Optional[List[ConceptualPlanStep]]]:
        """
        Генерирует концептуальный корректирующий план на основе информации о предыдущем неудачном выполнении.
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
        prompt_parts.append("\nПожалуйста, проанализируй ошибку и контекст. Твоя задача — создать НОВЫЙ КОНЦЕПТУАЛЬНЫЙ план действий, чтобы:")
        prompt_parts.append("\n1. Исправить возникшую ошибку ИЛИ обойти её, используя высокоуровневые концептуальные шаги.")
        prompt_parts.append("\n2. Попытаться достичь первоначальной цели пользователя, если это всё ещё возможно после исправления/обхода ошибки.")
        prompt_parts.append("\nЕсли ошибку исправить невозможно или первоначальная цель недостижима, объясни это в поле 'thought'.")
        prompt_parts.append("\nНовый план должен быть списком концептуальных шагов в JSON-формате, как описано в системных инструкциях (каждый шаг с 'goal', 'step_id', 'status':'pending', 'tool_logs':[], 'reason_for_status':null, 'final_result':null).")
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
            
            conceptual_plan_steps: List[ConceptualPlanStep] = []
            for i, step_raw in enumerate(plan_steps_raw):
                if not isinstance(step_raw, dict):
                    return (f"Ошибка: Шаг {i+1} в корректирующем плане не является словарем: {step_raw}. Мысль: {thought}", None)

                # Validate ConceptualPlanStep structure
                required_keys = {"step_id", "goal", "status", "reason_for_status", "tool_logs", "final_result"}
                if not required_keys.issubset(step_raw.keys()):
                    missing_keys = required_keys - step_raw.keys()
                    return (f"Ошибка: Шаг {i+1} в корректирующем плане не содержит обязательные ключи: {missing_keys}. Шаг: {step_raw}. Мысль: {thought}", None)

                if not isinstance(step_raw.get("goal"), str) or not step_raw.get("goal"):
                     return (f"Ошибка: 'goal' в корректирующем шаге {i+1} должен быть непустой строкой. Шаг: {step_raw}. Мысль: {thought}", None)
                if not isinstance(step_raw.get("step_id"), str) or not step_raw.get("step_id"):
                     return (f"Ошибка: 'step_id' в корректирующем шаге {i+1} должен быть непустой строкой. Шаг: {step_raw}. Мысль: {thought}", None)
                if step_raw.get("status") != "pending":
                     return (f"Ошибка: 'status' в корректирующем шаге {i+1} должен быть 'pending'. Шаг: {step_raw}. Мысль: {thought}", None)
                if step_raw.get("reason_for_status") is not None:
                     return (f"Ошибка: 'reason_for_status' в корректирующем шаге {i+1} должен быть null. Шаг: {step_raw}. Мысль: {thought}", None)
                if not isinstance(step_raw.get("tool_logs"), list) or step_raw.get("tool_logs"):
                     return (f"Ошибка: 'tool_logs' в корректирующем шаге {i+1} должен быть пустым списком. Шаг: {step_raw}. Мысль: {thought}", None)
                if step_raw.get("final_result") is not None:
                     return (f"Ошибка: 'final_result' в корректирующем шаге {i+1} должен быть null. Шаг: {step_raw}. Мысль: {thought}", None)
                
                conceptual_plan_steps.append(ConceptualPlanStep(**step_raw)) # type: ignore

            if not conceptual_plan_steps and thought: 
                return thought, None # This could be a valid case where Gemini explains why it can't correct
                
            return thought, conceptual_plan_steps

        except json.JSONDecodeError as e:
            error_context = json_string_to_parse if json_string_to_parse is not None else "Строка для парсинга не была определена (ошибка до присвоения)."
            error_msg = f"Ошибка декодирования JSON ответа от Gemini (корректировка): {e}\nСтрока для парсинга:\n{error_context}\nПолный ответ Gemini:\n{raw_response}"
            print(error_msg) 
            return error_msg, None
        except Exception as e:
            error_msg = f"Неожиданная ошибка при обработке ответа Gemini (корректировка): {e}\nПолный ответ Gemini:\n{raw_response}"
            print(error_msg)
            return error_msg, None

    def determine_next_action_for_goal(
        self,
        goal_description: str,
        history: Optional[List[Dict[str, str]]], # Overall conversation history (optional for prompt)
        goal_execution_log: List[ToolCallLogEntry], # Log of tool calls FOR THIS GOAL
        all_prior_conceptual_steps: Optional[List[ConceptualPlanStep]] = None # ADDED ARGUMENT
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]: # thought, next_tool_call, goal_status
        """
        Определяет следующее действие (вызов инструмента) для достижения цели или статус цели,
        учитывая результаты предыдущих концептуальных шагов.
        """
        if not self.gemini_client:
            return "Ошибка: Gemini клиент не инициализирован для определения следующего действия.", None, None

        # formatted_conversation_history = "" # Optional: Not used in the primary prompt for this method yet
        # if history:
        #     for message in history:
        #         formatted_conversation_history += f"{message['role'].capitalize()}: {message['content']}\n"
        #     formatted_conversation_history += "\n"
        
        formatted_prior_steps_summary = ""
        if all_prior_conceptual_steps:
            summary_parts = ["\n--- Обзор Результатов Предыдущих Концептуальных Шагов ---"]
            if not all_prior_conceptual_steps: # Should be caught by the outer if, but good for safety
                summary_parts.append("  (Нет выполненных предыдущих шагов)")
            else:
                for i, step in enumerate(all_prior_conceptual_steps):
                    summary_parts.append(f"  Предыдущий Шаг {i+1}: \"{step['goal']}\"")
                    summary_parts.append(f"    Статус: {step['status']}")
                    if step['reason_for_status']:
                        summary_parts.append(f"    Пояснение к статусу: {step['reason_for_status']}")
                    # if step['final_result'] is not None: # Keep commented as per instruction
                    #    summary_parts.append(f"    Итоговый результат шага: {json.dumps(step['final_result'], ensure_ascii=False, indent=2)}")
            formatted_prior_steps_summary = "\n".join(summary_parts) + "\n"


        formatted_log_entries = []
        if not goal_execution_log:
            formatted_log_entries.append("  Еще не было предпринято никаких действий для этой цели.")
        else:
            for i, log_entry in enumerate(goal_execution_log):
                entry_str = f"  Действие {i+1}:\n"
                entry_str += f"    Инструмент: {log_entry['tool_name']}({json.dumps(log_entry['args'], ensure_ascii=False)})\n"
                if log_entry['outcome_error']:
                    entry_str += f"    Результат: Ошибка - {log_entry['outcome_error']}\n"
                else:
                    # Ensure outcome_data is dumped with indent if it's complex, otherwise just convert to string
                    data_str = json.dumps(log_entry['outcome_data'], ensure_ascii=False, indent=2) if not isinstance(log_entry['outcome_data'], str) else log_entry['outcome_data']
                    entry_str += f"    Результат: {data_str}\n"
                formatted_log_entries.append(entry_str)
        formatted_log_string = "\n".join(formatted_log_entries)

        prompt_parts = [
            "Ты — ИИ-ассистент, отвечающий за определение СЛЕДУЮЩЕГО ДЕЙСТВИЯ для достижения конкретной цели. Тебе предоставлены доступные инструменты, описание цели, история уже предпринятых действий (включая их результаты) для этой цели, и ОБЗОР РЕЗУЛЬТАТОВ ПРЕДЫДУЩИХ КОНЦЕПТУАЛЬНЫХ ШАГОВ.",
            AVAILABLE_TOOLS_DESCRIPTIONS,
            formatted_prior_steps_summary, # Inserted summary of prior steps
            f"\n--- Текущая Цель ---\n{goal_description}\n",
            "--- История Действий для Этой Цели ---",
            formatted_log_string,
            "\n--- Твоя Задача ---",
            "Проанализируй цель, историю действий для этой цели, и ОБЗОР РЕЗУЛЬТАТОВ ПРЕДЫДУЩИХ КОНЦЕПТУАЛЬНЫХ ШАГОВ. Определи ОДНО следующее действие (вызов инструмента) ИЛИ реши, достигнута ли цель или она недостижима.",
            "ВАЖНО: Внимательно изучи ОБЗОР РЕЗУЛЬТАТОВ ПРЕДЫДУЩИХ КОНЦЕПТУАЛЬНЫХ ШАГОВ (если предоставлен). Если результат предыдущего шага делает текущую цель нелогичной, невыполнимой или уже достигнутой, ты ДОЛЖЕН это учесть. Например, если предыдущий шаг не нашел необходимый файл, не пытайся его читать в текущей цели, а укажи, что цель невыполнима из-за этого.",
            "Если цель уже достигнута на основе предыдущих действий или ОБЗОРА ПРЕДЫДУЩИХ ШАГОВ, или если она не может быть достигнута, укажи это.",
            "Если для достижения цели нужно выполнить еще одно действие, предложи вызов ОДНОГО инструмента.",
            "ВАЖНО: Не предлагай многошаговые планы здесь. Только ОДИН следующий вызов инструмента или статус цели.",
            "\n--- Формат Ответа ---",
            "Ответ должен быть строкой в формате JSON, содержащей:",
            "1. \"thought\": Твои размышления о текущем состоянии цели и почему ты выбираешь это действие или статус.",
            "2. ЛИБО \"next_tool_call\": Обьект со следующими ключами:",
            "   - \"tool_name\": (строка) Имя инструмента для вызова.",
            "   - \"args\": (словарь) Аргументы для этого инструмента.",
            "3. ЛИБО \"goal_status\": (строка) Установи в \"achieved\" если цель достигнута, или \"unachievable\" если цель не может быть достигнута.",
            "   - \"reason\": (строка, опционально) Краткое пояснение, почему цель достигнута или недостижима (особенно если 'unachievable').",
            "\nПримеры JSON ответа:",
            "Пример 1 (следующий шаг):",
            "{\"thought\": \"Нужно прочитать файл, указанный в логе.\", \"next_tool_call\": {\"tool_name\": \"read_file\", \"args\": {\"filepath\": \"docs/some_file.txt\"}}}",
            "Пример 2 (цель достигнута):",
            "{\"thought\": \"Вся необходимая информация собрана и обработана.\", \"goal_status\": \"achieved\", \"reason\": \"Файл успешно прочитан и его содержимое сохранено.\"}",
            "Пример 3 (цель недостижима):",
            "{\"thought\": \"Файл не найден после нескольких попыток, и нет информации для его создания.\", \"goal_status\": \"unachievable\", \"reason\": \"Файл не найден по указанному пути.\"}",
            # f"\nОбщая история диалога (для контекста, если нужно):\n{formatted_conversation_history}\n", # Optional
            "\n\nIMPORTANT: Your entire response for this specific turn MUST be a single, valid JSON object as described above. Start directly with '{' and end directly with '}'. Do not include any other text, explanations, conversational filler, or markdown formatting before or after the JSON object."
        ]
        full_request_to_gemini = "".join(prompt_parts)
        # print(f"\nDEBUG: Полный промпт для ОПРЕДЕЛЕНИЯ ДЕЙСТВИЯ Gemini:\n{full_request_to_gemini}\n")

        raw_response = self.gemini_client.send_prompt(full_request_to_gemini)

        if not raw_response:
            return "Не удалось получить ответ от Gemini для определения действия.", None, None
        if not isinstance(raw_response, str):
            return "Ошибка: Ответ от Gemini (определение действия) не является строкой.", None, None

        json_string_to_parse = None
        try:
            first_brace = raw_response.find('{')
            last_brace = raw_response.rfind('}')

            if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
                error_msg = f"Ошибка: Не удалось найти корректные ограничители JSON в ответе Gemini (определение действия).\nОтвет Gemini:\n{raw_response}"
                print(error_msg)
                return error_msg, None, None
            
            json_string_to_parse = raw_response[first_brace:last_brace+1]
            parsed_data = json.loads(json_string_to_parse)
            
            thought = parsed_data.get("thought")
            if not thought or not isinstance(thought, str):
                 print(f"Предупреждение: 'thought' отсутствует или не является строкой в ответе Gemini (определение действия): {parsed_data}")
                 thought = "Мысли отсутствуют или неверного формата."


            next_tool_call = parsed_data.get("next_tool_call")
            goal_status = parsed_data.get("goal_status")
            # reason = parsed_data.get("reason") # Reason is part of goal_status logic, not top level.

            if next_tool_call is not None:
                if not isinstance(next_tool_call, dict):
                    return f"Ошибка: 'next_tool_call' должен быть словарем, получен: {type(next_tool_call)}. Мысль: {thought}", None, None
                tool_name = next_tool_call.get("tool_name")
                args = next_tool_call.get("args")
                if not isinstance(tool_name, str) or not tool_name:
                    return f"Ошибка: 'tool_name' в 'next_tool_call' должен быть непустой строкой. Мысль: {thought}", None, None
                if not isinstance(args, dict):
                    return f"Ошибка: 'args' в 'next_tool_call' должен быть словарем. Мысль: {thought}", None, None
                # Optional: add reason to thought if goal_status is also somehow present, though prompt implies exclusivity
                # if goal_status and reason: thought += f" (Причина статуса: {reason})"
                return thought, next_tool_call, None
            
            elif goal_status is not None:
                if not isinstance(goal_status, str) or goal_status not in ["achieved", "unachievable"]:
                    return f"Ошибка: 'goal_status' должен быть 'achieved' или 'unachievable', получен: {goal_status}. Мысль: {thought}", None, None
                reason = parsed_data.get("reason")
                if reason and isinstance(reason, str):
                     thought += f" Причина: {reason}." # Append reason to thought for clarity
                return thought, None, goal_status
            
            else:
                return f"Ошибка: Ответ Gemini (определение действия) не содержит ни 'next_tool_call', ни 'goal_status'. Ответ: {json_string_to_parse}. Мысль: {thought}", None, None

        except json.JSONDecodeError as e:
            error_context = json_string_to_parse if json_string_to_parse is not None else "Строка для парсинга не была определена."
            error_msg = f"Ошибка декодирования JSON (определение действия): {e}\nСтрока: {error_context}\nПолный ответ: {raw_response}"
            print(error_msg) 
            return error_msg, None, None
        except Exception as e:
            error_msg = f"Неожиданная ошибка при обработке ответа Gemini (определение действия): {e}\nПолный ответ: {raw_response}"
            print(error_msg)
            return error_msg, None, None

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
            for i, step_item in enumerate(plan1):
                print(f"  Шаг {i+1} ({step_item['step_id']}): {step_item['goal']} (Status: {step_item['status']})")
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
            for i, step_item in enumerate(plan2):
                print(f"  Шаг {i+1} ({step_item['step_id']}): {step_item['goal']} (Status: {step_item['status']})")
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
            for i, step_item in enumerate(plan3):
                print(f"  Шаг {i+1} ({step_item['step_id']}): {step_item['goal']} (Status: {step_item['status']})")
        else:
            print("План не был сгенерирован.")
