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
MAX_CORRECTION_ATTEMPTS = 1 # Maximum attempts to correct a failed plan

def main_loop():
    print("Запуск основного цикла Autonomous Gemini Bot...")
    conversation_history: List[Dict[str, str]] = []
    try:
        ensure_workspace_exists()
    except Exception:
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    main_system_prompt_content = None
    client_system_prompt_path = os.path.join(script_dir, "prompts", "system_prompt.txt")
    if os.path.exists(client_system_prompt_path):
        try:
            with open(client_system_prompt_path, 'r', encoding='utf-8') as f:
                main_system_prompt_content = f.read().strip()
            if not main_system_prompt_content:
                print(f"ПРЕДУПРЕЖДЕНИЕ: Системный промпт в файле {client_system_prompt_path} пуст.")
                main_system_prompt_content = None # Ensure it's None if empty after stripping
            else:
                print(f"Содержимое системного промпта клиента загружено из {client_system_prompt_path}")
        except Exception as e:
            print(f"Ошибка при чтении файла системного промпта клиента {client_system_prompt_path}: {e}")
            main_system_prompt_content = None
    else:
        print(f"ПРЕДУПРЕЖДЕНИЕ: Файл системного промпта клиента {client_system_prompt_path} не найден.")

    gemini_cli = GeminiClient(system_prompt_text=main_system_prompt_content)

    if gemini_cli.system_prompt:
        print(f"Загруженный системный промпт КЛИЕНТА: {gemini_cli.system_prompt}")
    else:
        print("Системный промпт КЛИЕНТА не был загружен (либо файл не найден, пуст, или произошла ошибка при чтении).")

    planner = Planner() # Planner теперь сам управляет своим GeminiClient

    if not os.getenv('GOOGLE_API_KEY'):
        print("\nПРЕДУПРЕЖДЕНИЕ: Переменная окружения GOOGLE_API_KEY не установлена.")
        # return # Можно раскомментировать для строгой проверки

    print("\nВведите ваш запрос (или 'выход' для завершения):")
    
    original_user_request_for_correction = "" # Store the initial user request for correction context
    correction_attempts = 0 # Initialize correction attempts for each new user request cycle

    while True:
        try:
            # Only prompt for new input if not in a correction loop or if it's the first time
            if not original_user_request_for_correction or correction_attempts == 0:
                user_request = input("> ")
                if user_request.lower() == 'выход':
                    print("Завершение работы.")
                    break
                if not user_request:
                    continue
                original_user_request_for_correction = user_request # Save for potential correction later
                correction_attempts = 0 # Reset for new primary request
            else:
                # This means we are in a correction loop, use the original request
                user_request = original_user_request_for_correction
                # Do not reset correction_attempts here, it's incremented in the failure case

            # Add user request to history (only if it's a new primary request, not for corrections)
            # Correction prompts will be handled by the planner with full context.
            if correction_attempts == 0:
                conversation_history.append({"role": "user", "content": user_request})
            if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
            
            # Pass conversation_history to planner.generate_plan
            # This part will be skipped if we are in a correction loop and already have `plan_steps`
            if correction_attempts == 0: # Only generate a new plan if not correcting
                print("\nДумаю над вашим запросом...")
                thought_or_direct_answer, plan_steps = planner.generate_plan(user_request, history=conversation_history)

                if plan_steps is None: # This is the direct answer case from planner
                    print(f"Ответ Gemini (или мысли): {thought_or_direct_answer}")
                    if thought_or_direct_answer: # Ensure we don't append None
                        conversation_history.append({"role": "assistant", "content": thought_or_direct_answer})
                        if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                            conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                    original_user_request_for_correction = "" # Reset for next independent request
                    correction_attempts = 0 # Reset attempts
                    continue

                if thought_or_direct_answer:
                     print(f"Мои размышления по поводу задачи: {thought_or_direct_answer}")
                
                if not plan_steps: # Empty plan, but there was a thought_or_direct_answer
                    print("План не содержит шагов. Считаю задачу выполненной или не требующей действий.")
                    if thought_or_direct_answer: # Ensure we don't append None
                        conversation_history.append({"role": "assistant", "content": thought_or_direct_answer})
                        if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                            conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                    original_user_request_for_correction = "" # Reset for next independent request
                    correction_attempts = 0 # Reset attempts
                    continue
            # If plan_steps is already populated by a corrective plan, this block is skipped,
            # and we proceed to print and execute the corrective plan.

            print("\nСгенерирован следующий план (или корректирующий план):")
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
            
                    print(f"DEBUG: Неожиданный дополнительный план от Gemini: {final_plan}")
                
                correction_attempts = 0 # Reset on successful plan execution and summarization
                original_user_request_for_correction = "" # Clear the stored request

            else: # План не был успешно выполнен (error in execution_outcomes[-1])
                print("\nПлан не был полностью выполнен из-за ошибки на одном из шагов.")
                last_outcome = execution_outcomes[-1]
                error_message = last_outcome.get('error', 'Неизвестная ошибка в последнем шаге.')
                # failed_step_details = {"tool_name": last_outcome.get("tool_name"), "args": last_outcome.get("args")} # Not used directly by placeholder

                if correction_attempts >= MAX_CORRECTION_ATTEMPTS:
                    print("Достигнут лимит попыток исправления ошибки. План не может быть выполнен.")
                    print(f"Последняя ошибка: {error_message}")
                    # Add error message to history as assistant's final response for this attempt
                    final_error_response = f"Не удалось выполнить задачу после {MAX_CORRECTION_ATTEMPTS} попыток исправления. Последняя ошибка: {error_message}"
                    conversation_history.append({"role": "assistant", "content": final_error_response})
                    if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                         conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                    correction_attempts = 0 # Reset for the next user request
                    original_user_request_for_correction = "" # Reset for next user request
                    continue # To the next user request

                correction_attempts += 1
                print(f"Обнаружена ошибка: {error_message}. Попытка # {correction_attempts} сгенерировать корректирующий план...")

                # Placeholder call to planner.generate_correction_plan
                # Ensure original_user_request_for_correction is used for the original request context
                corrective_thought, corrective_plan_steps = planner.generate_plan( # Simulate with generate_plan for now
                    user_request=f"CONTEXT: The previous plan execution failed. Original user request was: '{original_user_request_for_correction}'. Failed plan outcomes: {json.dumps(execution_outcomes, ensure_ascii=False)}. The error was: '{error_message}'. Please generate a new plan to achieve the original request, considering this failure.",
                    history=conversation_history
                )

                if not corrective_plan_steps: # No corrective plan, or planner decided it cannot be fixed
                    response_to_user = corrective_thought or "Gemini не смог предложить корректирующий план."
                    print(response_to_user)
                    conversation_history.append({"role": "assistant", "content": response_to_user})
                    if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                        conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
                    correction_attempts = 0 # Reset attempts
                    original_user_request_for_correction = "" # Reset for next user request
                    continue # To the next user request
                else:
                    print("Получен корректирующий план. Попытка выполнения...")
                    plan_steps = corrective_plan_steps # Update plan_steps with the corrective plan
                    # The loop will continue, and execute_plan will be called with the new plan_steps
                    # thought_or_direct_answer is not directly used here, as we have a new plan
                    # We might want to print the corrective_thought if available
                    if corrective_thought:
                        print(f"Мысли по поводу корректирующего плана: {corrective_thought}")
                    continue # Re-enter the loop to execute the new plan_steps

        except KeyboardInterrupt:
            print("\nПрервано пользователем. Завершение работы.")
            original_user_request_for_correction = "" 
            correction_attempts = 0
            break
        except Exception as e:
            print(f"Произошла непредвиденная ошибка в основном цикле: {e}")


def main():
    print("Autonomous Gemini Bot started!")
    main_loop()

if __name__ == "__main__":
    main()
