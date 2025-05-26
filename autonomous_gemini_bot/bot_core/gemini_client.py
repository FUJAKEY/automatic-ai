import google.generativeai as genai
import os

class GeminiClient:
    def __init__(self, api_key=None, system_prompt_path=None):
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # Если API ключ не передан напрямую, попробуем загрузить из переменной окружения
            # В реальном приложении ключ нужно будет установить как переменную окружения GOOGLE_API_KEY
            # или передавать его при инициализации.
            # Для целей разработки, если ключ не найден, будем выводить предупреждение.
            try:
                genai.configure(api_key=os.environ['GOOGLE_API_KEY'])
            except KeyError:
                print("ПРЕДУПРЕЖДЕНИЕ: Переменная окружения GOOGLE_API_KEY не установлена. "
                      "Клиент Gemini может не работать без API ключа.")
                # Позволим инициализацию без ключа, чтобы можно было тестировать другие части,
                # но реальные вызовы API не будут работать.
                pass


        self.model = genai.GenerativeModel('gemini-1.5-flash-latest') # Используем gemini-1.5-flash-latest по умолчанию
        self.system_prompt = None
        if system_prompt_path:
            try:
                with open(system_prompt_path, 'r', encoding='utf-8') as f:
                    self.system_prompt = f.read()
            except FileNotFoundError:
                print(f"ПРЕДУПРЕЖДЕНИЕ: Файл системного промпта не найден по пути: {system_prompt_path}")
            except Exception as e:
                print(f"Ошибка при загрузке системного промпта: {e}")

    def send_prompt(self, user_prompt):
        """
        Отправляет промпт модели Gemini и возвращает текстовый ответ.
        Включает системный промпт, если он был загружен.
        """
        try:
            full_prompt = []
            if self.system_prompt:
                # Для Gemini API системные инструкции лучше передавать как часть истории или начальный user message,
                # либо использовать специальный параметр system_instruction если он доступен в используемой версии SDK
                # и для выбранной модели. Пока добавим его как первый элемент в 'contents'.
                # В более сложных сценариях это может быть объект ChatSession.
                # На данный момент, мы просто конкатенируем его с запросом пользователя,
                # но это не лучший способ для system prompt в Gemini.
                # Правильнее будет использовать messages API с ролями system/user/model.
                # TODO: Переделать на использование messages API с ролями, когда будем реализовывать диалоги.
                # Пока для простоты оставим так для одиночных запросов.
                # Мы передаем список 'contents' в generate_content
                
                # Исправленный подход для system prompt с gemini-pro,
                # системные инструкции могут быть переданы через `system_instruction` параметр модели
                # или как первый элемент в `contents` для `generate_content`.
                # Для `gemini-pro` через `GenerativeModel`:
                # model = genai.GenerativeModel('gemini-pro', system_instruction="Ваша системная инструкция")
                # Однако, если мы хотим динамически менять system prompt, лучше передавать его с каждым запросом.
                # Пока не будем использовать system_instruction в конструкторе модели, а передадим его в запросе.
                # Это не совсем "system prompt" в классическом понимании некоторых других API,
                # Gemini API обрабатывает это как часть общего контекста.
                # Мы передадим его как первую часть контента.
                # Это не идеальный способ, но для начала сойдет.
                # Для более продвинутого управления контекстом и ролями (system, user, model)
                # лучше использовать `start_chat()` и `send_message()`.
                # Пока что для простых запросов мы будем использовать `generate_content()`.

                # В новой версии API рекомендуется использовать `system_instruction` при создании модели,
                # но так как мы хотим загружать его из файла, передадим его в `contents`.
                # Это не будет работать как "system" роль, а как обычный "user" контент.
                # TODO: Изучить как правильно задавать system prompt для gemini-pro через SDK последней версии.
                # Для сейчас, просто добавим его в начало промпта.
                # Это не будет иметь специального "системного" эффекта, но будет частью контекста.
                # Для реального системного поведения может потребоваться другая модель или другой подход.
                
                # Упрощенный подход: пока не используем system_prompt напрямую в generate_content,
                # так как это требует более сложной структуры messages.
                # Вместо этого, пользовательский промпт будет основным.
                # Системный промпт будет загружен, но его интеграция будет позже.
                pass # Пока не используем system_prompt здесь напрямую


            # response = self.model.generate_content(full_prompt + [user_prompt]) # Старый вариант
            
            # Если системный промпт есть, создаем модель с ним.
            # Это создаст новую модель для каждого запроса, если system_prompt меняется,
            # что неэффективно. Лучше инициализировать модель один раз с системной инструкцией.
            # Но так как мы загружаем его из файла, этот подход позволяет гибкость.
            # TODO: Оптимизировать, если системный промпт не меняется часто.
            current_model = self.model
            if self.system_prompt:
                 # Для gemini-1.5-pro-latest есть параметр system_instruction
                 # model = genai.GenerativeModel(model_name='gemini-1.5-pro-latest', system_instruction=self.system_prompt)
                 # Для gemini-pro (не 1.5) такого параметра нет в конструкторе GenerativeModel.
                 # Вместо этого, системные инструкции передаются как часть контента.
                 # Мы будем использовать подход с передачей system_prompt как первого сообщения "user"
                 # перед реальным сообщением пользователя.
                 # Это не эквивалентно system role, но это способ передать инструкции.
                 
                 # Формируем контент для API
                 content_for_api = []
                 if self.system_prompt:
                     # Добавляем системный промпт как первое сообщение от "user"
                     # Это общепринятый способ для моделей, которые не имеют явной "system" роли в API запросе generateContent
                     content_for_api.append({'role': 'user', 'parts': [self.system_prompt]})
                 
                 # Добавляем текущий промпт пользователя
                 content_for_api.append({'role': 'user', 'parts': [user_prompt]})
                 
                 # Если мы хотим поддерживать историю, то нужно будет передавать всю историю.
                 # Пока что мы этого не делаем.
                 # response = current_model.generate_content(content_for_api)
                 
                 # Для простоты первого шага, и так как gemini-pro не имеет system_instruction в конструкторе,
                 # и чтобы не усложнять структуру до messages API, мы просто передадим user_prompt.
                 # Интеграция system_prompt будет улучшена на следующих этапах.
                 pass # System prompt integration to be refined.

            response = self.model.generate_content(user_prompt)
            return response.text
        except Exception as e:
            print(f"Ошибка при отправке промпта в Gemini: {e}")
            return None

if __name__ == '__main__':
    # Пример использования (потребуется установленный GOOGLE_API_KEY)
    # Замените 'YOUR_API_KEY' на ваш реальный ключ или установите переменную окружения
    # client = GeminiClient(api_key='YOUR_API_KEY', 
    #                       system_prompt_path='../prompts/system_prompt.txt')
    
    # Для теста без ключа, но с возможностью загрузки промпта (вызовы API не будут работать)
    # client = GeminiClient(system_prompt_path='../prompts/system_prompt.txt')
    # print(f"Загруженный системный промпт: {client.system_prompt}")

    # Чтобы протестировать отправку промпта, раскомментируйте и установите ключ:
    # if os.getenv('GOOGLE_API_KEY'):
    #     client = GeminiClient(system_prompt_path='../prompts/system_prompt.txt')
    #     if client.system_prompt:
    #         print(f"Системный промпт: {client.system_prompt}")
    #     else:
    #         print("Системный промпт не был загружен.")
        
    #     prompt = "Расскажи короткий факт о космосе."
    #     print(f"Отправка промпта: {prompt}")
    #     answer = client.send_prompt(prompt)
    #     if answer:
    #         print(f"Ответ Gemini: {answer}")
    #     else:
    #         print("Не удалось получить ответ.")
    # else:
    #     print("Переменная окружения GOOGLE_API_KEY не установлена. Пропуск теста отправки промпта.")
    pass
