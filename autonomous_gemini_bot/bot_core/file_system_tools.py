import os
import subprocess

# Определим рабочую директорию для операций с файлами.
# Это сделано для безопасности, чтобы бот не мог получить доступ ко всей файловой системе.
# Все пути к файлам будут считаться относительно этой директории.
# При запуске из main.py, который находится в autonomous_gemini_bot/,
# эта директория будет /app/autonomous_gemini_bot/workspace/
# Важно: Эта директория должна существовать или быть создана при инициализации бота.
WORKING_DIRECTORY = "workspace" 

def _get_safe_path(filepath: str) -> str:
    """
    Преобразует относительный путь в безопасный абсолютный путь внутри WORKING_DIRECTORY.
    Предотвращает выход за пределы рабочей директории.
    """
    # Нормализуем путь, чтобы убрать .. и т.п.
    normalized_filepath = os.path.normpath(filepath)
    
    # Запрещаем абсолютные пути и пути, выходящие за пределы рабочей директории
    if os.path.isabs(normalized_filepath) or normalized_filepath.startswith(".."):
        raise ValueError(f"Недопустимый путь к файлу: {filepath}. Разрешены только относительные пути внутри рабочей директории.")

    # Создаем полный путь
    # __file__ указывает на file_system_tools.py
    # os.path.dirname(__file__) -> bot_core
    # os.path.dirname(os.path.dirname(__file__)) -> autonomous_gemini_bot
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Убедимся, что рабочая директория существует
    workspace_path = os.path.join(base_dir, WORKING_DIRECTORY)
    if not os.path.exists(workspace_path):
        try:
            os.makedirs(workspace_path)
            print(f"Создана рабочая директория: {workspace_path}")
        except Exception as e:
            # Если не удалось создать, это проблема, но _get_safe_path не должен падать здесь
            # Ошибка возникнет при попытке использовать путь позже.
            # Лучше обрабатывать создание директории при инициализации бота.
            print(f"Ошибка при создании рабочей директории {workspace_path}: {e}")


    full_path = os.path.join(workspace_path, normalized_filepath)
    
    # Еще раз проверяем, что путь не вышел за пределы workspace_path после соединения
    if not os.path.abspath(full_path).startswith(os.path.abspath(workspace_path)):
        raise ValueError(f"Попытка доступа за пределы рабочей директории: {filepath}")
        
    return full_path

from typing import Tuple, Optional, List, Any

def execute_terminal_command(command: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Выполняет команду в терминале в контексте WORKING_DIRECTORY.
    Возвращает кортеж (result_data, error_message).
    result_data: строка с stdout и stderr, если успешно.
    error_message: строка с описанием ошибки, если неуспешно.
    Опасно! Эту функцию нужно использовать с большой осторожностью.
    """
    # TODO: Добавить дополнительные меры безопасности. Например, белый список разрешенных команд.
    if not command:
        return None, "Ошибка: Команда не может быть пустой."
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_path = os.path.join(base_dir, WORKING_DIRECTORY)
        if not os.path.exists(workspace_path):
            os.makedirs(workspace_path, exist_ok=True)
            
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=workspace_path,
            timeout=30
        )
        if process.returncode == 0:
            return f"Команда выполнена успешно.\nStdout:\n{process.stdout}\nStderr:\n{process.stderr}", None
        else:
            return None, f"Ошибка выполнения команды (код {process.returncode}).\nStdout:\n{process.stdout}\nStderr:\n{process.stderr}"
    except subprocess.TimeoutExpired:
        return None, "Ошибка: Время выполнения команды истекло."
    except Exception as e:
        return None, f"Исключение при выполнении команды: {e}"

def read_file(filepath: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Читает содержимое файла.
    Возвращает кортеж (file_content, error_message).
    file_content: строка с содержимым файла, если успешно.
    error_message: строка с описанием ошибки, если неуспешно.
    """
    if not filepath:
        return None, "Ошибка: Путь к файлу не может быть пустым."
    try:
        safe_path = _get_safe_path(filepath)
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content, None
    except FileNotFoundError:
        return None, f"Ошибка: Файл не найден по пути '{filepath}' (внутри {WORKING_DIRECTORY})."
    except ValueError as ve:
        return None, str(ve)
    except Exception as e:
        return None, f"Ошибка при чтении файла '{filepath}': {e}"

def write_to_file(filepath: str, content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Записывает/создает файл с указанным содержимым.
    Возвращает кортеж (success_message, error_message).
    success_message: строка с сообщением об успехе.
    error_message: строка с описанием ошибки, если неуспешно.
    """
    if not filepath:
        return None, "Ошибка: Путь к файлу не может быть пустым."
    try:
        safe_path = _get_safe_path(filepath)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Файл успешно записан: '{filepath}' (внутри {WORKING_DIRECTORY}).", None
    except ValueError as ve:
        return None, str(ve)
    except Exception as e:
        return None, f"Ошибка при записи в файл '{filepath}': {e}"

def create_directory(path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Создает новую директорию.
    Возвращает кортеж (success_message, error_message).
    success_message: строка с сообщением об успехе.
    error_message: строка с описанием ошибки, если неуспешно.
    """
    if not path:
        return None, "Ошибка: Путь для создания директории не может быть пустым."
    try:
        safe_path = _get_safe_path(path)
        if os.path.exists(safe_path):
            return None, f"Ошибка: Директория или файл уже существует по пути '{path}' (внутри {WORKING_DIRECTORY})."
        os.makedirs(safe_path)
        return f"Директория успешно создана: '{path}' (внутри {WORKING_DIRECTORY}).", None
    except ValueError as ve:
        return None, str(ve)
    except Exception as e:
        return None, f"Ошибка при создании директории '{path}': {e}"

def list_directory_contents(path: str = ".") -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Возвращает список файлов и директорий по указанному пути.
    Возвращает кортеж (items_list, error_message).
    items_list: список строк с именами файлов/директорий, если успешно. Директории имеют '/' в конце.
    error_message: строка с описанием ошибки, если неуспешно.
    """
    try:
        safe_path = _get_safe_path(path)
        if not os.path.isdir(safe_path):
            return None, f"Ошибка: '{path}' не является директорией (внутри {WORKING_DIRECTORY})."
        
        items = os.listdir(safe_path)
        if not items:
            return [], None # Успех, но директория пуста
        
        processed_items = []
        for item in items:
            if os.path.isdir(os.path.join(safe_path, item)):
                processed_items.append(item + "/")
            else:
                processed_items.append(item)
        return processed_items, None
    except ValueError as ve:
        return None, str(ve)
    except FileNotFoundError:
        return None, f"Ошибка: Директория не найдена по пути '{path}' (внутри {WORKING_DIRECTORY})."
    except Exception as e:
        return None, f"Ошибка при просмотре содержимого директории '{path}': {e}"

if __name__ == '__main__':
    # Тестирование функций
    current_script_path = os.path.abspath(__file__)
    bot_core_dir = os.path.dirname(current_script_path)
    project_root_dir = os.path.dirname(bot_core_dir)
    
    workspace_abs_path = os.path.join(project_root_dir, WORKING_DIRECTORY)
    if not os.path.exists(workspace_abs_path):
        os.makedirs(workspace_abs_path)
        print(f"Создана тестовая рабочая директория: {workspace_abs_path}")

    print("--- Тестирование функций файловой системы ---")
    print(f"Все операции будут выполняться в '{WORKING_DIRECTORY}/'")

    def print_result(data: Optional[Any], error: Optional[str]):
        if error:
            print(f"  Ошибка: {error}")
        elif data is not None: # data может быть пустой строкой или списком, что не False
            if isinstance(data, list):
                if not data:
                    print("  Результат: Директория пуста.")
                else:
                    print("  Результат (список):")
                    for item in data:
                        print(f"    - {item}")
            else:
                 print(f"  Результат: {data}")
        else: # Должно быть либо data, либо error, но на всякий случай
            print("  Неожиданный результат: нет ни данных, ни ошибки.")


    print("\n1. Создание директории 'test_dir':")
    data, error = create_directory("test_dir")
    print_result(data, error)

    print("\n1a. Создание директории '' (пустой путь):")
    data, error = create_directory("")
    print_result(data, error)

    print("\n2. Повторное создание директории 'test_dir':")
    data, error = create_directory("test_dir") # Должна быть ошибка
    print_result(data, error)

    print("\n3. Создание вложенной директории 'test_dir/inner_dir':")
    data, error = create_directory("test_dir/inner_dir")
    print_result(data, error)

    print("\n4. Запись в файл 'test_file.txt' в 'test_dir':")
    data, error = write_to_file("test_dir/test_file.txt", "Привет, мир!\nЭто тестовый файл.")
    print_result(data, error)
    
    print("\n4a. Запись в файл с пустым путем '':")
    data, error = write_to_file("", "Не должно записаться")
    print_result(data, error)

    print("\n5. Чтение файла 'test_dir/test_file.txt':")
    data, error = read_file("test_dir/test_file.txt")
    print_result(data, error)

    print("\n5a. Чтение файла с пустым путем '':")
    data, error = read_file("")
    print_result(data, error)

    print("\n6. Чтение несуществующего файла 'non_existent_file.txt':")
    data, error = read_file("non_existent_file.txt")
    print_result(data, error)

    print("\n7. Просмотр содержимого директории 'test_dir':")
    data, error = list_directory_contents("test_dir")
    print_result(data, error)
    
    print("\n8. Просмотр содержимого корневой рабочей директории ('.') :")
    # Создадим там временный файл для проверки непустого листинга
    write_to_file("temp_root_file.txt", "temp")
    data, error = list_directory_contents(".")
    print_result(data, error)
    # Удалим временный файл
    if os.path.exists(_get_safe_path("temp_root_file.txt")):
        os.remove(_get_safe_path("temp_root_file.txt"))

    print("\n8a. Просмотр содержимого пустой созданной директории 'empty_dir':")
    create_directory("empty_dir")
    data, error = list_directory_contents("empty_dir")
    print_result(data, error)
    # Удалим empty_dir
    if os.path.exists(_get_safe_path("empty_dir")):
        os.rmdir(_get_safe_path("empty_dir"))


    print("\n9. Просмотр содержимого несуществующей директории 'non_existent_dir':")
    data, error = list_directory_contents("non_existent_dir")
    print_result(data, error)

    print("\n10. Попытка записи файла за пределами рабочей директории (должна быть ошибка):")
    data, error = write_to_file("../outside_file.txt", "Этот файл не должен быть создан")
    print_result(data, error)
    
    outside_file_path = os.path.join(os.path.dirname(workspace_abs_path), "outside_file.txt")
    if os.path.exists(outside_file_path):
        print(f"  ОШИБКА БЕЗОПАСНОСТИ: Файл '{outside_file_path}' был создан за пределами рабочей директории!")
    else:
        print("  Тест безопасности пройден: файл за пределами рабочей директории не создан.")


    print("\n11. Выполнение команды терминала (ls или dir):")
    command_to_run = "ls -la" if os.name != 'nt' else "dir"
    print(f"  Выполнение команды: {command_to_run}")
    data, error = execute_terminal_command(command_to_run)
    print_result(data, error)

    print("\n11a. Выполнение команды терминала с пустым вводом:")
    data, error = execute_terminal_command("")
    print_result(data, error)
    
    print("\n12. Выполнение опасной команды (rm -rf / или аналогичной):")
    print("  Тест опасной команды пропущен (для безопасности).")

    print("\n--- Очистка тестовых файлов и директорий ---")
    try:
        if os.path.exists(_get_safe_path("test_dir/test_file.txt")):
            os.remove(_get_safe_path("test_dir/test_file.txt"))
        if os.path.exists(_get_safe_path("test_dir/inner_dir")):
            os.rmdir(_get_safe_path("test_dir/inner_dir"))
        if os.path.exists(_get_safe_path("test_dir")):
            os.rmdir(_get_safe_path("test_dir"))
        print("  Тестовые файлы и директории удалены.")
    except Exception as e:
        print(f"  Ошибка при очистке: {e}")

    print("\n--- Тестирование завершено ---")
