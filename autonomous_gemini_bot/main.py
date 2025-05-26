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
from bot_core.plan_structures import ConceptualPlanStep, ToolCallLogEntry 
import uuid # For generating step_ids if not provided by Planner
from datetime import datetime, timezone # For timestamps in ToolCallLogEntry
from typing import List, Dict, Any, Tuple, Optional 

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

# --- New Conceptual Plan Executor ---
def execute_conceptual_plan(
    conceptual_plan: List[ConceptualPlanStep],
    planner: Planner, 
    conversation_history: List[Dict[str, str]], 
    available_functions: Dict[str, callable]
) -> Tuple[List[ConceptualPlanStep], Optional[str]]:
    """
    Выполняет концептуальный план, взаимодействуя с Planner для определения конкретных шагов.
    Возвращает обновленный концептуальный план и опциональное сообщение о глобальной ошибке,
    если какой-либо шаг не удалось выполнить и требуется коррекция всего плана.
    """
    current_conceptual_plan = conceptual_plan 
    MAX_ACTIONS_PER_GOAL = 5 

    print("\n--- Начало выполнения концептуального плана ---")

    for i, concept_step in enumerate(current_conceptual_plan):
        # Ensure 'tool_logs' exists and is a list, as per ConceptualPlanStep definition
        # and other fields are initialized if they were somehow missing from planner output
        # (though planner validation should catch this)
        if 'tool_logs' not in concept_step or not isinstance(concept_step.get('tool_logs'), list):
            concept_step['tool_logs'] = []
        if 'status' not in concept_step: # Should be 'pending' from planner
             concept_step['status'] = 'pending'
        if 'reason_for_status' not in concept_step:
             concept_step['reason_for_status'] = None
        if 'final_result' not in concept_step:
            concept_step['final_result'] = None


        if concept_step['status'] in ['achieved', 'failed_terminal']:
            print(f"Концептуальный шаг ({i+1}/{len(current_conceptual_plan)}) '{concept_step['goal']}' уже выполнен ранее со статусом '{concept_step['status']}'. Пропуск.")
            continue
        
        # If a step was marked for correction by a previous execution, it should be handled by main_loop's correction mechanism
        # before re-entering execute_conceptual_plan with a (potentially new) plan.
        # So, we assume 'failed_needs_correction' means it's a fresh attempt or a corrected plan being executed.
        
        print(f"\nВыполнение концептуального шага ({i+1}/{len(current_conceptual_plan)}): {concept_step['goal']}")
        concept_step['status'] = 'in_progress'
        concept_step['reason_for_status'] = "Выполняется..."


        for action_count in range(MAX_ACTIONS_PER_GOAL):
            print(f"  Попытка действия {action_count + 1}/{MAX_ACTIONS_PER_GOAL} для цели: {concept_step['goal']}")
            
            action_thought, next_tool_call, goal_status_update = planner.determine_next_action_for_goal(
                goal_description=concept_step['goal'],
                history=conversation_history, 
                goal_execution_log=concept_step['tool_logs']
            )

            if action_thought:
                print(f"    Мысли планировщика (для действия): {action_thought}")

            if goal_status_update:
                concept_step['status'] = goal_status_update
                # The reason from planner.determine_next_action_for_goal's thought is usually good here.
                # Planner.py appends "Причина: <reason>" to thought for goal_status updates.
                concept_step['reason_for_status'] = action_thought 
                
                if goal_status_update == "achieved":
                    # Populate final_result if achieved.
                    if concept_step['tool_logs'] and not concept_step['tool_logs'][-1]['outcome_error']:
                        last_log_data = concept_step['tool_logs'][-1]['outcome_data']
                        concept_step['final_result'] = last_log_data if last_log_data is not None else "Действие выполнено, нет специфичных данных для результата."
                    elif action_thought and "Причина:" not in action_thought : 
                         concept_step['final_result'] = action_thought
                    else:
                        concept_step['final_result'] = "Цель достигнута (нет специфичных данных от последнего шага или детальной мысли планировщика)."
                
                print(f"    Концептуальный шаг '{concept_step['goal']}' завершен со статусом: {goal_status_update}. Пояснение: {concept_step['reason_for_status']}")
                break # Break from actions loop for this conceptual step

            elif next_tool_call:
                tool_name = next_tool_call.get('tool_name')
                tool_args = next_tool_call.get('args', {})
                
                print(f"      Следующее действие: вызов инструмента '{tool_name}' с аргументами {json.dumps(tool_args, ensure_ascii=False)}")

                current_tool_log_entry = ToolCallLogEntry(
                    tool_name=str(tool_name), 
                    args=dict(tool_args),    
                    outcome_data=None,
                    outcome_error=None,
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

                if tool_name in available_functions:
                    try:
                        function_to_call = available_functions[tool_name]
                        tool_data, tool_error_msg_str = function_to_call(**tool_args)
                        
                        current_tool_log_entry['outcome_data'] = tool_data
                        current_tool_log_entry['outcome_error'] = tool_error_msg_str

                        if tool_error_msg_str:
                            print(f"        Ошибка инструмента '{tool_name}': {tool_error_msg_str}")
                        else:
                            print(f"        Результат инструмента '{tool_name}': {json.dumps(tool_data, ensure_ascii=False, indent=2)}")
                    
                    except Exception as e:
                        tool_error_msg_str = f"Неожиданная ошибка при вызове инструмента '{tool_name}': {str(e)}"
                        print(f"        {tool_error_msg_str}")
                        current_tool_log_entry['outcome_error'] = tool_error_msg_str
                else:
                    tool_error_msg_str = f"Инструмент '{tool_name}' не найден."
                    print(f"        {tool_error_msg_str}")
                    current_tool_log_entry['outcome_error'] = tool_error_msg_str
                
                concept_step['tool_logs'].append(current_tool_log_entry)

            else: 
                print("    Ошибка: Планировщик не вернул ни следующего действия, ни статуса цели.")
                concept_step['status'] = 'failed_needs_correction' 
                concept_step['reason_for_status'] = "Планировщик не смог определить следующее действие или статус цели после предыдущих попыток."
                return current_conceptual_plan, f"Планировщик не смог определить действие для цели: '{concept_step['goal']}'" 
        
        else: # Inner loop (action_count) completed without break (i.e., MAX_ACTIONS_PER_GOAL reached)
            if concept_step['status'] == 'in_progress': 
                print(f"  Достигнут лимит действий ({MAX_ACTIONS_PER_GOAL}) для концептуального шага: {concept_step['goal']}")
                concept_step['status'] = 'failed_needs_correction'
                concept_step['reason_for_status'] = f"Достигнут лимит действий ({MAX_ACTIONS_PER_GOAL}) для достижения этой цели."
        
        if concept_step['status'] in ['failed_needs_correction', 'failed_terminal']:
            error_detail = f"Концептуальный шаг '{concept_step['goal']}' не удалось выполнить (статус: {concept_step['status']}). Причина: {concept_step.get('reason_for_status', 'Нет деталей')}"
            print(f"  {error_detail}")
            return current_conceptual_plan, error_detail

    print("\n--- Выполнение концептуального плана успешно завершено (все шаги обработаны) ---")
    return current_conceptual_plan, None


MAX_HISTORY_EXCHANGES = 5
MAX_MAIN_CORRECTION_ATTEMPTS = 1

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
                main_system_prompt_content = None 
            else:
                print(f"Содержимое системного промпта клиента загружено из {client_system_prompt_path}")
        except Exception as e:
            print(f"Ошибка при чтении файла системного промпта клиента {client_system_prompt_path}: {e}")
            main_system_prompt_content = None
    else:
        print(f"ПРЕДУПРЕЖДЕНИЕ: Файл системного промпта клиента {client_system_prompt_path} не найден.")

    # This GeminiClient is for the main assistant's direct responses (if any, currently planner handles all)
    # The Planner instantiates its own GeminiClient with its specific system prompt.
    # _ = GeminiClient(system_prompt_text=main_system_prompt_content) # Keep if used directly, or remove
    
    planner = Planner() 

    if not os.getenv('GOOGLE_API_KEY'):
        print("\nПРЕДУПРЕЖДЕНИЕ: Переменная окружения GOOGLE_API_KEY не установлена.")

    print("\nВведите ваш запрос (или 'выход' для завершения):")
    
    original_user_request_for_correction = "" 
    main_correction_attempts = 0 
    
    conceptual_plan_steps: Optional[List[ConceptualPlanStep]] = None # Holds the current conceptual plan

    while True:
        try:
            if not original_user_request_for_correction or main_correction_attempts == 0:
                user_request = input("> ")
                if user_request.lower() == 'выход':
                    print("Завершение работы.")
                    break
                if not user_request:
                    continue
                original_user_request_for_correction = user_request 
                main_correction_attempts = 0 
                conceptual_plan_steps = None # Clear previous plan for a new request
                if conversation_history and conversation_history[-1]['role'] == 'user' and conversation_history[-1]['content'] == user_request:
                    pass # Avoid duplicating user message if it's the same as last one (e.g. after a correction)
                else:
                     conversation_history.append({"role": "user", "content": user_request})

            else: # We are in a correction loop for the main plan
                user_request = original_user_request_for_correction
            
            if len(conversation_history) > MAX_HISTORY_EXCHANGES * 2:
                conversation_history = conversation_history[-(MAX_HISTORY_EXCHANGES * 2):]
            
            if not conceptual_plan_steps: # Only generate a new plan if one isn't already being corrected/executed
                print("\nДумаю над вашим запросом (генерация концептуального плана)...")
                thought_or_direct_answer, new_plan_steps = planner.generate_plan(user_request, history=conversation_history)

                if new_plan_steps is None: 
                    print(f"Ответ Gemini (или мысли): {thought_or_direct_answer}")
                    if thought_or_direct_answer: 
                        conversation_history.append({"role": "assistant", "content": thought_or_direct_answer})
                    original_user_request_for_correction = "" 
                    main_correction_attempts = 0 
                    continue

                if thought_or_direct_answer:
                     print(f"Мои размышления по поводу задачи: {thought_or_direct_answer}")
                
                if not new_plan_steps: 
                    print("План не содержит шагов. Считаю задачу выполненной или не требующей действий.")
                    if thought_or_direct_answer: 
                        conversation_history.append({"role": "assistant", "content": thought_or_direct_answer})
                    original_user_request_for_correction = "" 
                    main_correction_attempts = 0 
                    continue
                conceptual_plan_steps = new_plan_steps


            print("\n--- Текущий концептуальный план ---")
            if not conceptual_plan_steps: # Should not happen if logic above is correct
                 print("Ошибка: Концептуальный план отсутствует перед выполнением.")
                 original_user_request_for_correction = "" 
                 main_correction_attempts = 0
                 continue

            for i, step_detail in enumerate(conceptual_plan_steps):
                print(f"  Шаг {i+1} ({step_detail.get('step_id', 'N/A')}): {step_detail.get('goal','N/A')} (Статус: {step_detail.get('status','N/A')})")
            
            updated_conceptual_plan, execution_error_message = execute_conceptual_plan(
                conceptual_plan_steps, planner, conversation_history, AVAILABLE_FUNCTIONS
            )
            conceptual_plan_steps = updated_conceptual_plan # Keep the mutated plan with updated statuses/logs

            if execution_error_message: # A conceptual step failed and requires plan-level correction
                print(f"\nОшибка выполнения концептуального плана: {execution_error_message}")
                main_correction_attempts += 1
                
                if main_correction_attempts >= MAX_MAIN_CORRECTION_ATTEMPTS:
                    final_error_msg = f"Достигнут лимит ({MAX_MAIN_CORRECTION_ATTEMPTS}) попыток исправления концептуального плана. Завершение попыток для запроса: '{original_user_request_for_correction}'. Последняя ошибка: {execution_error_message}"
                    print(final_error_msg)
                    conversation_history.append({"role": "assistant", "content": final_error_msg})
                    original_user_request_for_correction = "" 
                    main_correction_attempts = 0 
                    conceptual_plan_steps = None # Clear plan
                    continue 

                print(f"Попытка # {main_correction_attempts} сгенерировать корректирующий КОНЦЕПТУАЛЬНЫЙ план...")
                
                # Pass the entire current (failed) conceptual plan as failed_plan_outcomes context
                corrective_thought, new_conceptual_correction_plan = planner.generate_correction_plan(
                    original_user_request=original_user_request_for_correction,
                    history=conversation_history,
                    failed_plan_outcomes=conceptual_plan_steps, # Send the whole plan with its current states
                    error_message=execution_error_message 
                )

                if new_conceptual_correction_plan:
                    print("Получен корректирующий концептуальный план. Попытка выполнения...")
                    if corrective_thought: print(f"Мысли по поводу корректирующего плана: {corrective_thought}")
                    conceptual_plan_steps = new_conceptual_correction_plan # Replace the old plan
                    # Loop continues to re-attempt execute_conceptual_plan with the new plan
                else:
                    no_correction_msg = corrective_thought or "Gemini не смог предложить корректирующий концептуальный план."
                    print(no_correction_msg)
                    conversation_history.append({"role": "assistant", "content": no_correction_msg})
                    original_user_request_for_correction = "" 
                    main_correction_attempts = 0
                    conceptual_plan_steps = None # Clear plan
                    continue
            
            else: # Conceptual plan executed without returning a global error message
                print("\nКонцептуальный план выполнен (все шаги обработаны или помечены как завершенные). Формирую итоговый ответ...")
                main_correction_attempts = 0 # Reset on successful execution path

                context_for_summarization = f"Первоначальный запрос пользователя был: '{original_user_request_for_correction}'.\nБыл выполнен следующий концептуальный план:\n"
                all_steps_achieved = True
                for i, step in enumerate(conceptual_plan_steps):
                    context_for_summarization += f"\nШаг {i+1}: Цель: {step['goal']}\n"
                    context_for_summarization += f"  Статус: {step['status']}\n"
                    if step['reason_for_status']:
                        context_for_summarization += f"  Пояснение к статусу: {step['reason_for_status']}\n"
                    if step['final_result'] is not None:
                        context_for_summarization += f"  Итоговый результат шага: {json.dumps(step['final_result'], ensure_ascii=False, indent=2)}\n"
                    
                    context_for_summarization += "  Лог действий:\n"
                    if not step['tool_logs']:
                        context_for_summarization += "    (Не было предпринято действий с инструментами для этой цели)\n"
                    else:
                        for j, log_entry in enumerate(step['tool_logs']):
                            context_for_summarization += f"    Действие {j+1}: {log_entry['tool_name']}({json.dumps(log_entry['args'], ensure_ascii=False)})"
                            if log_entry['outcome_error']:
                                context_for_summarization += f" -> Ошибка: {log_entry['outcome_error']}\n"
                            else:
                                context_for_summarization += f" -> Результат: {json.dumps(log_entry['outcome_data'], ensure_ascii=False, indent=2)}\n"
                    if step['status'] != 'achieved':
                        all_steps_achieved = False
                
                if not all_steps_achieved:
                     context_for_summarization += "\nПримечание: Не все концептуальные шаги были успешно достигнуты."
                
                context_for_summarization += "\n\nПожалуйста, проанализируй результаты и предоставь окончательный ответ на первоначальный запрос пользователя."
                
                final_thought, final_direct_answer_plan = planner.generate_plan(context_for_summarization, history=conversation_history)
                
                if final_thought:
                    print(f"\nИтоговый ответ Gemini:\n{final_thought}")
                    conversation_history.append({"role": "assistant", "content": final_thought})
                else:
                    print("\nGemini не предоставил итогового ответа.")
                
                if final_direct_answer_plan: # Should be None or empty from planner in "summarization" mode
                    print(f"DEBUG: Неожиданный дополнительный план от Gemini при суммаризации: {final_direct_answer_plan}")

                original_user_request_for_correction = "" # Clear for next independent request
                conceptual_plan_steps = None # Clear plan

        except KeyboardInterrupt:
            print("\nПрервано пользователем. Завершение работы.")
            break
        except Exception as e:
            print(f"Произошла непредвиденная ошибка в основном цикле: {type(e).__name__} - {e}")
            import traceback
            traceback.print_exc() # Print full traceback for debugging
            original_user_request_for_correction = "" # Reset state to avoid loop with bad data
            main_correction_attempts = 0
            conceptual_plan_steps = None


def main():
    print("Autonomous Gemini Bot started!")
    main_loop()

if __name__ == "__main__":
    main()
