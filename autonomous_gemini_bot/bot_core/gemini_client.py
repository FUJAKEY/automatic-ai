import google.generativeai as genai
import os
from typing import Optional
import time
import google.api_core.exceptions 
# Might also need: from google.auth import exceptions as auth_exceptions for other specific errors if desired later

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

    def send_prompt(self, user_prompt: str, max_retries: int = 2, initial_retry_delay_seconds: int = 30):
        """
        Отправляет промпт модели Gemini и возвращает текстовый ответ.
        Включает механизм повторных попыток при ошибках, связанных с квотами (429).
        Системный промпт обрабатывается на уровне инициализации модели.
        """
        retries = 0
        current_delay = initial_retry_delay_seconds

        while retries <= max_retries:
            try:
                if not self.model: # Ensure model is initialized
                    error_msg = "Ошибка: Модель Gemini не инициализирована в клиенте."
                    print(error_msg)
                    return error_msg # Return error string

                print(f"Попытка отправки промпта в Gemini (попытка {retries + 1}/{max_retries + 1})...")
                response = self.model.generate_content(user_prompt)
                return response.text
            
            except google.api_core.exceptions.ResourceExhausted as e: # Handles 429 errors
                print(f"Ошибка квоты (429) при отправке промпта в Gemini: {e}")
                
                actual_retry_delay = current_delay # Default to current backoff delay
                try:
                    # Attempt to extract specific retry delay from error details
                    if hasattr(e, 'retry_delay') and hasattr(e.retry_delay, 'seconds'):
                        # This structure was hinted at by user logs: "retry_delay { seconds: 49 }"
                        # Accessing e.retry_delay.seconds directly if the object structure supports it.
                        # Note: google.api_core.exceptions.RetryInfo might be part of e.args or e.grpc_status_details
                        # For google.generativeai, direct attribute access might not be standard.
                        # Let's assume it's directly available or via a known attribute if the library structures it.
                        # If `e.retry_delay` is itself the RetryInfo object:
                        if isinstance(e.retry_delay, google.api_core.exceptions.RetryInfo) and e.retry_delay.retry_delay:
                             actual_retry_delay_duration = e.retry_delay.retry_delay
                             actual_retry_delay = int(actual_retry_delay_duration.total_seconds())
                             print(f"API предложил задержку: {actual_retry_delay} секунд (из RetryInfo).")
                        elif hasattr(e.retry_delay, 'seconds'): # Fallback for a simple seconds attribute
                             actual_retry_delay = e.retry_delay.seconds
                             print(f"API предложил задержку: {actual_retry_delay} секунд (из e.retry_delay.seconds).")
                        else:
                            # Try extracting from metadata if available (common in other Google libs)
                            if hasattr(e, 'metadata') and e.metadata:
                                for item in e.metadata:
                                    if hasattr(item, 'key') and item.key == 'retry-after' and hasattr(item, 'value'):
                                        actual_retry_delay = int(item.value)
                                        print(f"API предложил задержку: {actual_retry_delay} секунд (из metadata).")
                                        break
                    else: # If e.retry_delay is not present or doesn't have .seconds
                        print(f"Атрибут e.retry_delay.seconds не найден. Используем текущую задержку {current_delay} сек.")

                except Exception as parse_ex:
                    print(f"Не удалось извлечь специфичную задержку из ошибки API, используем {actual_retry_delay} сек. Ошибка парсинга: {parse_ex}")


                if retries < max_retries:
                    print(f"Ожидание {actual_retry_delay} секунд перед следующей попыткой ({retries + 2}/{max_retries + 1})...") # Corrected retry count display
                    time.sleep(actual_retry_delay)
                    retries += 1
                    current_delay *= 2 # Exponential backoff for subsequent generic retries
                else:
                    print("Достигнут лимит повторных попыток для ошибок квоты.")
                    return f"Ошибка: Достигнут лимит повторных попыток ({max_retries}) после ошибки квоты (429). Последняя ошибка: {e}"

            except Exception as e:
                # Handle other types of exceptions (network, auth, etc.)
                error_msg = f"Непредвиденная ошибка при отправке промпта в Gemini: {type(e).__name__} - {e}"
                print(error_msg)
                # Depending on the error, you might not want to retry.
                # For now, other errors are not retried.
                return f"Ошибка: Непредвиденная ошибка при взаимодействии с Gemini API: {type(e).__name__} - {e}"
        
        # This part should ideally be unreachable if max_retries leads to returning an error string above.
        # However, as a fallback if loop exits unexpectedly:
        final_error_msg = f"Ошибка: Не удалось получить ответ от Gemini после {max_retries + 1} попыток."
        print(final_error_msg)
        return final_error_msg

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
