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

def execute_terminal_command(command: str) -> str:
    """
    Выполняет команду в терминале в контексте WORKING_DIRECTORY и возвращает ее вывод (stdout и stderr).
    Опасно! Эту функцию нужно использовать с большой осторожностью.
    """
    # TODO: Добавить дополнительные меры безопасности. Например, белый список разрешенных команд.
    # Сейчас функция позволяет выполнить любую команду, что небезопасно.
    if not command:
        return "Ошибка: Команда не может быть пустой."
    try:
        # Убедимся, что рабочая директория существует для выполнения команды
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_path = os.path.join(base_dir, WORKING_DIRECTORY)
        if not os.path.exists(workspace_path):
            os.makedirs(workspace_path, exist_ok=True)
            
        # Выполняем команду
        # Важно: `shell=True` может быть небезопасным, если команда формируется из ненадежного источника.
        # Для большей безопасности лучше передавать команду как список аргументов (shell=False).
        # Но для простоты "терминальной команды" пока оставим shell=True.
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=workspace_path, # Выполняем команду в рабочей директории
            timeout=30  # Таймаут для предотвращения зависания
        )
        if process.returncode == 0:
            return f"Команда выполнена успешно.\nStdout:\n{process.stdout}\nStderr:\n{process.stderr}"
        else:
            return f"Ошибка выполнения команды (код {process.returncode}).\nStdout:\n{process.stdout}\nStderr:\n{process.stderr}"
    except subprocess.TimeoutExpired:
        return "Ошибка: Время выполнения команды истекло."
    except Exception as e:
        return f"Исключение при выполнении команды: {e}"

def read_file(filepath: str) -> str:
    """Читает содержимое файла и возвращает его."""
    if not filepath:
        return "Ошибка: Путь к файлу не может быть пустым."
    try:
        safe_path = _get_safe_path(filepath)
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return f"Ошибка: Файл не найден по пути '{filepath}' (внутри {WORKING_DIRECTORY})."
    except ValueError as ve: # Ошибка из _get_safe_path
        return str(ve)
    except Exception as e:
        return f"Ошибка при чтении файла '{filepath}': {e}"

def write_to_file(filepath: str, content: str) -> str:
    """Записывает/создает файл с указанным содержимым."""
    if not filepath:
        return "Ошибка: Путь к файлу не может быть пустым."
    try:
        safe_path = _get_safe_path(filepath)
        # Убедимся, что директория для файла существует
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Файл успешно записан: '{filepath}' (внутри {WORKING_DIRECTORY})."
    except ValueError as ve: # Ошибка из _get_safe_path
        return str(ve)
    except Exception as e:
        return f"Ошибка при записи в файл '{filepath}': {e}"

def create_directory(path: str) -> str:
    """Создает новую директорию."""
    if not path:
        return "Ошибка: Путь для создания директории не может быть пустым."
    try:
        safe_path = _get_safe_path(path)
        if os.path.exists(safe_path):
            return f"Ошибка: Директория или файл уже существует по пути '{path}' (внутри {WORKING_DIRECTORY})."
        os.makedirs(safe_path)
        return f"Директория успешно создана: '{path}' (внутри {WORKING_DIRECTORY})."
    except ValueError as ve: # Ошибка из _get_safe_path
        return str(ve)
    except Exception as e:
        return f"Ошибка при создании директории '{path}': {e}"

def list_directory_contents(path: str = ".") -> str:
    """Возвращает список файлов и директорий по указанному пути (по умолчанию текущая рабочая директория)."""
    try:
        # Если path ".", это текущая директория workspace.
        # Если path не ".", то это поддиректория внутри workspace.
        safe_path = _get_safe_path(path)
        if not os.path.isdir(safe_path):
            return f"Ошибка: '{path}' не является директорией (внутри {WORKING_DIRECTORY})."
        
        items = os.listdir(safe_path)
        if not items:
            return f"Директория '{path}' пуста (внутри {WORKING_DIRECTORY})."
        
        # Добавим слеш к директориям для наглядности
        processed_items = []
        for item in items:
            if os.path.isdir(os.path.join(safe_path, item)):
                processed_items.append(item + "/")
            else:
                processed_items.append(item)
        return f"Содержимое директории '{path}' (внутри {WORKING_DIRECTORY}):\n" + "\n".join(processed_items)
    except ValueError as ve: # Ошибка из _get_safe_path
        return str(ve)
    except FileNotFoundError: # Если сама директория path не найдена после _get_safe_path (маловероятно, если _get_safe_path отработал)
        return f"Ошибка: Директория не найдена по пути '{path}' (внутри {WORKING_DIRECTORY})."
    except Exception as e:
        return f"Ошибка при просмотре содержимого директории '{path}': {e}"

if __name__ == '__main__':
    # Тестирование функций
    # Создадим директорию workspace, если она не существует, на уровне autonomous_gemini_bot/
    # Это нужно для локального тестирования file_system_tools.py
    # В реальном сценарии это будет сделано при инициализации бота или _get_safe_path
    
    # Путь к директории /autonomous_gemini_bot/
    current_script_path = os.path.abspath(__file__) # .../autonomous_gemini_bot/bot_core/file_system_tools.py
    bot_core_dir = os.path.dirname(current_script_path) # .../autonomous_gemini_bot/bot_core/
    project_root_dir = os.path.dirname(bot_core_dir) # .../autonomous_gemini_bot/
    
    workspace_abs_path = os.path.join(project_root_dir, WORKING_DIRECTORY)
    if not os.path.exists(workspace_abs_path):
        os.makedirs(workspace_abs_path)
        print(f"Создана тестовая рабочая директория: {workspace_abs_path}")

    print("--- Тестирование функций файловой системы ---")
    print(f"Все операции будут выполняться в '{WORKING_DIRECTORY}/'")

    # Перед тестами убедимся, что workspace чист или содержит только то, что нужно
    # Для простоты, можно вручную очищать перед запуском этого скрипта, если нужно.

    print("\n1. Создание директории 'test_dir':")
    print(create_directory("test_dir"))

    print("\n2. Повторное создание директории 'test_dir':")
    print(create_directory("test_dir")) # Должна быть ошибка

    print("\n3. Создание вложенной директории 'test_dir/inner_dir':")
    # Сначала убедимся что test_dir существует
    # _get_safe_path("test_dir") # Это создаст test_dir, если его нет, из-за логики в _get_safe_path
                               # Нет, _get_safe_path создает только сам WORKING_DIRECTORY, а не поддиректории.
                               # create_directory должен сам создавать.
    # Если test_dir не была создана успешно на шаге 1, этот шаг может провалиться.
    # Лучше делать create_directory("test_dir/inner_dir") напрямую, т.к. makedirs создаст промежуточные.
    print(create_directory("test_dir/inner_dir"))


    print("\n4. Запись в файл 'test_file.txt' в 'test_dir':")
    print(write_to_file("test_dir/test_file.txt", "Привет, мир!\nЭто тестовый файл."))

    print("\n5. Чтение файла 'test_dir/test_file.txt':")
    content = read_file("test_dir/test_file.txt")
    print(content)

    print("\n6. Чтение несуществующего файла 'non_existent_file.txt':")
    print(read_file("non_existent_file.txt"))

    print("\n7. Просмотр содержимого директории 'test_dir':")
    print(list_directory_contents("test_dir"))
    
    print("\n8. Просмотр содержимого корневой рабочей директории ('.') :")
    print(list_directory_contents("."))
    
    print("\n9. Просмотр содержимого несуществующей директории 'non_existent_dir':")
    print(list_directory_contents("non_existent_dir"))

    print("\n10. Попытка записи файла за пределами рабочей директории (должна быть ошибка):")
    print(write_to_file("../outside_file.txt", "Этот файл не должен быть создан"))
    # Проверим, что он действительно не создан
    outside_file_path = os.path.join(os.path.dirname(workspace_abs_path), "outside_file.txt")
    if os.path.exists(outside_file_path):
        print(f"ОШИБКА БЕЗОПАСНОСТИ: Файл '{outside_file_path}' был создан за пределами рабочей директории!")
        # os.remove(outside_file_path) # Удалить для чистоты
    else:
        print("Тест безопасности пройден: файл за пределами рабочей директории не создан.")


    print("\n11. Выполнение команды терминала (ls или dir):")
    # ВНИМАНИЕ: Эта команда выполняется в рабочей директории.
    # Для Windows: 'dir', для Linux/macOS: 'ls -la'
    # Эта команда безопасна, но будьте осторожны с другими командами.
    command_to_run = "ls -la" if os.name != 'nt' else "dir"
    print(f"Выполнение команды: {command_to_run}")
    print(execute_terminal_command(command_to_run))
    
    print("\n12. Выполнение опасной команды (rm -rf / или аналогичной):")
    # Мы не будем ее выполнять, но здесь нужно помнить о рисках.
    # print(execute_terminal_command("echo 'Это тест опасной команды, но она не должна ничего удалять'"))
    # print(execute_terminal_command("mkdir test_command_dir && echo 'hello' > test_command_dir/file.txt && ls test_command_dir && rm -r test_command_dir"))
    print("Тест опасной команды пропущен (для безопасности).")


    print("\n--- Тестирование завершено ---")
    # При желании можно добавить код для очистки созданных файлов и директорий
    # Например:
    # os.remove(_get_safe_path("test_dir/test_file.txt"))
    # os.rmdir(_get_safe_path("test_dir/inner_dir"))
    # os.rmdir(_get_safe_path("test_dir"))
    # print("Тестовые файлы и директории удалены.")
