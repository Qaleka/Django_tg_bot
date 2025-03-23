#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import threading  # Для запуска бота в отдельном потоке
from bot_app.telegram_bot import start_bot
from django.core.cache import cache

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bauman_event_tg_bot.settings')

    # Запуск бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    try:
        # Проверяем доступность ключей в кэше
        cache.set("test_key", "test_value", timeout=5)
        value = cache.get("test_key")
        if value == "test_value":
            print("Successfully connected to Redis!")
        else:
            print("Redis connection test failed: Unable to retrieve test value.")
    except Exception as e:
        print(f"Redis connection error: {e}")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()