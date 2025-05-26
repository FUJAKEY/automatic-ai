import google.generativeai as genai
import os
from typing import Optional

class GeminiClient:
    def __init__(self, api_key=None, system_prompt_text: Optional[str] = None):
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

        # Determine the model name based on the environment variable
        env_model_name = os.getenv('gemini_model')
        if env_model_name:
            model_name = env_model_name
            print(f"GeminiClient: Using model from environment variable: {model_name}")
        else:
            model_name = 'gemini-1.5-flash-latest'
            print(f"GeminiClient: Using default model: {model_name}")

        self.system_prompt = system_prompt_text # Store the provided system prompt text

        if self.system_prompt:
            self.model = genai.GenerativeModel(model_name, system_instruction=self.system_prompt)
            print(f"GeminiClient: Model initialized with provided system prompt.")
        else:
            self.model = genai.GenerativeModel(model_name)
            print(f"GeminiClient: Model initialized without a system prompt.")

    def send_prompt(self, user_prompt):
        """
        Отправляет промпт модели Gemini и возвращает текстовый ответ.
        Системный промпт обрабатывается на уровне инициализации модели.
        """
        try:
            response = self.model.generate_content(user_prompt)
            return response.text
        except Exception as e:
            print(f"Ошибка при отправке промпта в Gemini: {e}")
            return None

if __name__ == '__main__':
    # Пример использования (потребуется установленный GOOGLE_API_KEY)
    # Замените 'YOUR_API_KEY' на ваш реальный ключ или установите переменную окружения
    # client = GeminiClient(api_key='YOUR_API_KEY',
    #                       system_prompt_text='Это пример системного промпта.')

    # Для теста без ключа, но с возможностью использования системного промпта (вызовы API не будут работать)
    # client = GeminiClient(system_prompt_text='Это пример системного промпта для теста.')
    # print(f"Используемый системный промпт: {client.system_prompt}")

    # Чтобы протестировать отправку промпта, раскомментируйте и установите ключ:
    # if os.getenv('GOOGLE_API_KEY'):
    #     client = GeminiClient(system_prompt_text='Ты полезный ассистент.')
    #     if client.system_prompt:
    #         print(f"Системный промпт: {client.system_prompt}")
    #     else:
    #         print("Системный промпт не был предоставлен.")

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
