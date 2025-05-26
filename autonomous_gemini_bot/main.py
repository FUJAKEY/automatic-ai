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
    Выполняет шаги плана автоматически.
    Возвращает True, если все шаги завершились успешно, иначе False.
    """
    if not plan_steps:
        print("План пуст, нечего выполнять.")
        return True

    print("\nНачало автоматического выполнения плана...")
    all_steps_succeeded = True

    for i, step in enumerate(plan_steps):
        print(f"  Выполнение шага {i+1}/{len(plan_steps)}: {step.get('tool_name')}({json.dumps(step.get('args'), ensure_ascii=False)})")

        tool_name = step.get("tool_name")
        args = step.get("args")

        if tool_name in AVAILABLE_FUNCTIONS:
            try:
                function_to_call = AVAILABLE_FUNCTIONS[tool_name]
                result = function_to_call(**args)
                print(f"      Результат: {result}")
                if isinstance(result, str) and result.startswith("Ошибка:"):
                    all_steps_succeeded = False
                    print(f"      Шаг {i+1} ({tool_name}) завершился с ошибкой. Выполнение плана прервано.")
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
            print(f"    Ошибка: Инструмент '{tool_name}' не найден. Выполнение плана прервано.")
            all_steps_succeeded = False
            break
    
    if all_steps_succeeded:
        print("\nПлан успешно выполнен!")
        return True
    else:
        print("\nВыполнение плана было прервано из-за ошибки.")
        return False


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
