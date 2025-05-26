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

def execute_plan(plan_steps: list):
    """
    Выполняет шаги плана с возможностью выбора режима выполнения.
    Возвращает True, если все выполненные шаги (не пропущенные) завершились успешно, иначе False.
    """
    if not plan_steps:
        print("План пуст, нечего выполнять.")
        return True

    print("\nВыберите режим выполнения плана:")
    print("1. Выполнить все шаги автоматически.")
    print("2. Выполнить пошагово (с подтверждением перед каждым шагом).")
    print("3. Отменить выполнение плана.")

    choice = input("Ваш выбор (1-3): ")

    if choice == '3':
        print("Выполнение плана отменено.")
        return False # Считаем это неуспешным выполнением, так как пользователь отменил

    if choice not in ['1', '2']:
        print("Неверный выбор. Выполнение плана отменено.")
        return False

    skipped_steps_indices = set()
    if choice == '2': # Пошаговое выполнение
        while True:
            print("\nУправление пошаговым выполнением:")
            print("Введите номер шага для пропуска (например, 'п1', 'п2', ...).")
            print("Введите 'сброс' для отмены всех пропусков.")
            print("Введите 'старт' для начала пошагового выполнения.")
            print("Введите 'отмена' для отмены выполнения плана.")
            
            step_control_choice = input("Действие по шагам: ").lower()

            if step_control_choice == 'отмена':
                print("Выполнение плана отменено.")
                return False
            elif step_control_choice == 'старт':
                break
            elif step_control_choice == 'сброс':
                skipped_steps_indices.clear()
                print("Все пропуски шагов отменены.")
            elif step_control_choice.startswith('п'):
                try:
                    step_num_to_skip = int(step_control_choice[1:]) -1 # -1 для 0-индексации
                    if 0 <= step_num_to_skip < len(plan_steps):
                        skipped_steps_indices.add(step_num_to_skip)
                        print(f"Шаг {step_num_to_skip+1} будет пропущен.")
                    else:
                        print("Неверный номер шага для пропуска.")
                except ValueError:
                    print("Неверный формат для пропуска шага. Используйте 'пНОМЕР'.")
            else:
                print("Неизвестная команда.")

    print("\nНачало выполнения плана...")
    all_steps_succeeded = True
    # confirm_step используется для проверки, был ли план отменен в пошаговом режиме
    # Инициализируем её значением, которое не вызовет прерывания, если мы не в пошаговом режиме
    confirm_step = "да" 

    for i, step in enumerate(plan_steps):
        if i in skipped_steps_indices:
            print(f"  Пропуск шага {i+1}: {step.get('tool_name')}({json.dumps(step.get('args'), ensure_ascii=False)})")
            continue

        print(f"  Выполнение шага {i+1}/{len(plan_steps)}: {step.get('tool_name')}({json.dumps(step.get('args'), ensure_ascii=False)})")

        if choice == '2': # Пошаговый режим с подтверждением
            confirm_step = input("    Выполнить этот шаг? (да/нет/пропустить/отменить план): ").lower()
            if confirm_step == 'нет':
                print("    Шаг пропущен пользователем.")
                # Не считаем это ошибкой плана, просто пользователь решил не выполнять
                continue 
            elif confirm_step == 'пропустить':
                print("    Шаг пропущен пользователем.")
                skipped_steps_indices.add(i) # Запомним, если вдруг будет возврат (пока не реализовано)
                continue
            elif confirm_step == 'отменить план':
                print("Выполнение плана прервано пользователем.")
                all_steps_succeeded = False # План не выполнен до конца
                break # Выходим из цикла выполнения шагов

        tool_name = step.get("tool_name")
        args = step.get("args")

        if tool_name in AVAILABLE_FUNCTIONS:
            try:
                function_to_call = AVAILABLE_FUNCTIONS[tool_name]
                result = function_to_call(**args)
                print(f"      Результат: {result}")
                if isinstance(result, str) and result.startswith("Ошибка:"):
                    all_steps_succeeded = False
                    print(f"      Шаг {i+1} завершился с ошибкой. Выполнение плана прервано.")
                    break
            except TypeError as te:
                print(f"      Ошибка вызова функции {tool_name}: неверные аргументы. {te}")
                all_steps_succeeded = False
                break
            except Exception as e:
                print(f"      Неожиданная ошибка при выполнении шага {tool_name}: {e}")
                all_steps_succeeded = False
                break
        else:
            print(f"    Ошибка: Инструмент '{tool_name}' не найден.")
            all_steps_succeeded = False
            break
    
    if all_steps_succeeded and choice != '3' and (choice == '1' or (choice == '2' and confirm_step != 'отменить план')):
        # Условие стало сложнее, т.к. all_steps_succeeded может быть True, если все оставшиеся шаги были пропущены
        # Нужно проверить, был ли хотя бы один шаг выполнен успешно или все пропущены/отменены
        # Простая проверка: если мы дошли досюда и all_steps_succeeded все еще True, и не было отмены, то все ок.
        print("\nПлан (или его часть) успешно выполнен!")
        return True # Возвращаем True, если не было ошибок в выполненных шагах
    elif not all_steps_succeeded:
        print("\nВыполнение плана было прервано из-за ошибки или отменено пользователем на одном из шагов.")
        return False
    else: # Сюда попадаем, если, например, все шаги были пропущены или план был отменен до начала
        print("\nВыполнение плана завершено (возможно, не все шаги были выполнены).")
        return True # Если ошибок не было, но и не все выполнено - считаем условно успешным


def main_loop():
    print("Запуск основного цикла Autonomous Gemini Bot...")
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

            print("\nДумаю над вашим запросом...")
            thought_or_direct_answer, plan_steps = planner.generate_plan(user_request)

            if plan_steps is None:
                print(f"Ответ Gemini (или мысли): {thought_or_direct_answer}")
                continue

            if thought_or_direct_answer:
                 print(f"Мои размышления по поводу задачи: {thought_or_direct_answer}")
            
            if not plan_steps:
                print("План не содержит шагов. Считаю задачу выполненной или не требующей действий.")
                continue

            print("\nСгенерирован следующий план:")
            for i, step in enumerate(plan_steps):
                print(f"  Шаг {i+1}: {step['tool_name']}({json.dumps(step['args'], ensure_ascii=False)})")
            
            # Выполнение плана перенесено в отдельную функцию
            execute_plan(plan_steps)

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
