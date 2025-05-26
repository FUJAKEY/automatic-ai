from bot_core.gemini_client import GeminiClient
from bot_core.planner import Planner
from bot_core.file_system_tools import (
    execute_terminal_command,
    read_file,
    write_to_file,
    create_directory,
    list_directory_contents
)
import os
import json # Для вывода словарей в красивом виде

# Словарь, связывающий имена инструментов с их функциями
AVAILABLE_FUNCTIONS = {
    "execute_terminal_command": execute_terminal_command,
    "read_file": read_file,
    "write_to_file": write_to_file,
    "create_directory": create_directory,
    "list_directory_contents": list_directory_contents,
}

def ensure_workspace_exists():
    """ Гарантирует, что директория workspace существует. """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_path = os.path.join(script_dir, "workspace")
    if not os.path.exists(workspace_path):
        try:
            os.makedirs(workspace_path)
            print(f"Создана рабочая директория: {workspace_path}")
        except Exception as e:
            print(f"Критическая ошибка: Не удалось создать рабочую директорию {workspace_path}: {e}")
            raise

from typing import List, Dict, Any, Tuple # Added for type hinting

def execute_plan(plan_steps: list) -> List[Dict[str, Any]]:
    """
    Выполняет шаги плана автоматически и агрегирует результаты.
    Возвращает список словарей, каждый из которых представляет результат выполнения одного шага.
    Каждый словарь содержит ключи: "tool_name", "args", "data" (результат от инструмента), 
    и "error" (сообщение об ошибке, если есть).
    В случае ошибки на каком-либо шаге, выполнение плана прерывается, 
    и возвращается список результатов, собранных до этого момента (включая ошибочный шаг).
    """
    if not plan_steps:
        print("План пуст, нечего выполнять.")
        return []

    print("\nНачало автоматического выполнения плана...")
    aggregated_results: List[Dict[str, Any]] = []

    for i, step in enumerate(plan_steps):
        tool_name = step.get("tool_name")
        args = step.get("args")
        
        print(f"  Выполнение шага {i+1}/{len(plan_steps)}: {tool_name}({json.dumps(args, ensure_ascii=False)})")

        step_outcome: Dict[str, Any] = {
            "tool_name": tool_name,
            "args": args,
            "data": None,
            "error": None
        }

        if tool_name in AVAILABLE_FUNCTIONS:
            try:
                function_to_call = AVAILABLE_FUNCTIONS[tool_name]
                # file_system_tools functions now return (data, error_message)
                data, error_message = function_to_call(**args)
                
                step_outcome["data"] = data
                step_outcome["error"] = error_message

                if error_message:
                    print(f"      Ошибка: {error_message}")
                    aggregated_results.append(step_outcome)
                    print(f"      Выполнение плана прервано на шаге {i+1} из-за ошибки.")
                    return aggregated_results
                elif data is not None:
                    # Для list_directory_contents, data может быть пустым списком, что нормально
                    if isinstance(data, list) and not data:
                         print("      Результат: Директория пуста или команда не вернула вывод.")
                    else:
                        print(f"      Результат: {data}")
                else:
                    # Случай, когда data is None и error_message is None
                    print("      Шаг выполнен успешно (нет специфичных данных для вывода).")

            except TypeError as te:
                error_msg = f"Ошибка вызова функции {tool_name}: неверные аргументы. {te}"
                print(f"      {error_msg}")
                step_outcome["error"] = error_msg
                aggregated_results.append(step_outcome)
                print(f"      Выполнение плана прервано на шаге {i+1}.")
                return aggregated_results
            except Exception as e:
                error_msg = f"Неожиданная ошибка при выполнении шага {tool_name}: {e}"
                print(f"      {error_msg}")
                step_outcome["error"] = error_msg
                aggregated_results.append(step_outcome)
                print(f"      Выполнение плана прервано на шаге {i+1}.")
                return aggregated_results
        else:
            error_msg = f"Инструмент '{tool_name}' не найден."
            print(f"    Ошибка: {error_msg}")
            step_outcome["error"] = error_msg
            aggregated_results.append(step_outcome)
            print(f"    Выполнение плана прервано на шаге {i+1}.")
            return aggregated_results
        
        aggregated_results.append(step_outcome)

    # Если цикл завершился без прерываний (т.е. все шаги успешны)
    print("\nВсе шаги плана выполнены.") # Сообщение о завершении, но не обязательно об успехе каждого шага
                                         # Успех определяется анализом aggregated_results вызывающей стороной
    return aggregated_results

MAX_HISTORY_EXCHANGES = 5

def main_loop():
    print("Запуск основного цикла Autonomous Gemini Bot...")
    conversation_history: List[Dict[str, str]] = []
    try:
        ensure_workspace_exists()
    except Exception:
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    client_system_prompt_path = os.path.join(script_dir, "prompts", "system_prompt.txt")

    if not os.path.exists(client_system_prompt_path):
        print(f"ПРЕДУПРЕЖДЕНИЕ: Файл системного промпта клиента {client_system_prompt_path} не найден.")
        gemini_cli = GeminiClient()
    else:
        print(f"Файл системного промпта клиента найден: {client_system_prompt_path}")
        gemini_cli = GeminiClient(system_prompt_path=client_system_prompt_path)

    if gemini_cli.system_prompt:
        print(f"Загруженный системный промпт КЛИЕНТА: {gemini_cli.system_prompt}")
    else:
        print("Системный промпт КЛИЕНТА не был загружен.")

    planner = Planner(gemini_cli)

    if not os.getenv('GOOGLE_API_KEY'):
        print("\nПРЕДУПРЕЖДЕНИЕ: Переменная окружения GOOGLE_API_KEY не установлена.")
        # return # Можно раскомментировать для строгой проверки

    print("\nВведите ваш запрос (или 'выход' для завершения):")
    while True:
        try:
            user_request = input("> ")
            if user_request.lower() == 'выход':
                print("Завершение работы.")
                break
            if not user_request:
                continue

            # Add user request to history
            conversation_history.append({"role": "user", "content": user_request})
            if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
            
            # Pass conversation_history to planner.generate_plan
            print("\nДумаю над вашим запросом...")
            thought_or_direct_answer, plan_steps = planner.generate_plan(user_request, history=conversation_history)

            if plan_steps is None: # This is the direct answer case from planner
                print(f"Ответ Gemini (или мысли): {thought_or_direct_answer}")
                if thought_or_direct_answer: # Ensure we don't append None
                    conversation_history.append({"role": "assistant", "content": thought_or_direct_answer})
                    if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                        conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                continue

            if thought_or_direct_answer:
                 print(f"Мои размышления по поводу задачи: {thought_or_direct_answer}")
            
            if not plan_steps: # Empty plan, but there was a thought_or_direct_answer
                print("План не содержит шагов. Считаю задачу выполненной или не требующей действий.")
                # This thought_or_direct_answer is the AI's response for an empty plan.
                if thought_or_direct_answer: # Ensure we don't append None
                    conversation_history.append({"role": "assistant", "content": thought_or_direct_answer})
                    if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                        conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                continue

            print("\nСгенерирован следующий план:")
            for i, step in enumerate(plan_steps):
                print(f"  Шаг {i+1}: {step['tool_name']}({json.dumps(step['args'], ensure_ascii=False)})")
            
            # Выполнение плана
            execution_outcomes = execute_plan(plan_steps)

            # Определяем успешность выполнения плана
            plan_successful = (
                execution_outcomes and 
                execution_outcomes[-1].get("error") is None
            )

            if plan_successful:
                print("\nПлан выполнен успешно. Формирую итоговый ответ...")
                # Конструируем контекст для итогового ответа от планировщика
                context_for_summarization = (
                    f"Первоначальный запрос пользователя был: '{user_request}'.\n"
                    f"Был выполнен следующий план из {len(plan_steps)} шагов:\n"
                )
                for i, step_cfg in enumerate(plan_steps): # Renamed step to step_cfg to avoid conflict
                    context_for_summarization += f"  Шаг {i+1}: {step_cfg['tool_name']}({json.dumps(step_cfg['args'], ensure_ascii=False)})\n"
                
                context_for_summarization += "\nРезультаты выполнения шагов:\n"
                for i, outcome in enumerate(execution_outcomes):
                    outcome_data_str = ""
                    # Prioritize error message if it exists
                    if outcome.get('error') is not None:
                        outcome_data_str = f"  Ошибка: {outcome['error']}"
                    elif outcome.get('data') is not None:
                        # Handle empty list case for data (e.g. list_directory_contents on empty dir)
                        if isinstance(outcome['data'], list) and not outcome['data']:
                            outcome_data_str = "  Данные: (пустой список или нет вывода)"
                        else:
                            outcome_data_str = f"  Данные: {json.dumps(outcome['data'], ensure_ascii=False, indent=2)}"
                    else: # No error, no data
                        outcome_data_str = "  (нет специфичных данных или ошибки)"
                    
                    context_for_summarization += f"  Результат шага {i+1} ({outcome['tool_name']}): {outcome_data_str}\n"

                context_for_summarization += "\nПожалуйста, проанализируй результаты и предоставь окончательный ответ на первоначальный запрос пользователя."
                
                # print(f"\nDEBUG: Контекст для суммаризации:\n{context_for_summarization}\n") # Для отладки
                
                final_thought, final_plan = planner.generate_plan(context_for_summarization, history=conversation_history)
                
                # Ожидаем, что final_plan будет None или пустым, а final_thought - ответом.
                if final_thought:
                    print(f"\nИтоговый ответ Gemini:\n{final_thought}")
                    conversation_history.append({"role": "assistant", "content": final_thought})
                    if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                        conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                else:
                    print("\nGemini не предоставил итогового ответа.")
                    # Optionally, add a generic "I could not generate a final response" to history
                    # For now, only adding if final_thought is present.
                if final_plan:
                    print(f"DEBUG: Неожиданный дополнительный план от Gemini: {final_plan}")
            
            # This 'elif not plan_steps:' block is now handled before plan execution.
            # The case where plan_steps is an empty list (not None) and has a thought
            # is now handled by the 'if not plan_steps:' block after planner.generate_plan call.

            else: # План не был успешно выполнен (error in execution_outcomes[-1])
                print("\nПлан не был полностью выполнен из-за ошибки на одном из шагов. "
                      "Результаты выполнения (если есть) были выведены выше.")
                # We don't add a new "assistant" message here as the errors from execute_plan are already printed.
                # The summarization step (which would generate a new assistant message) was skipped.

        except KeyboardInterrupt:
            print("\nПрервано пользователем. Завершение работы.")
            break
        except Exception as e:
            print(f"Произошла непредвиденная ошибка в основном цикле: {e}")


def main():
    print("Autonomous Gemini Bot started!")
    main_loop()

if __name__ == "__main__":
    main()
