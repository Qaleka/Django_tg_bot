import os
from celery import Celery
from django.conf import settings
from celery.schedules import crontab

# Указываем путь к настройкам Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bauman_event_tg_bot.settings')

# Создаем экземпляр Celery
app = Celery('bot_app')

# Загружаем настройки из Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Регистрируем периодические задачи
app.conf.beat_schedule = {
    'delete-past-events': {
        'task': 'bot_app.tasks.delete_past_non_recurring_events',
        'schedule': crontab(minute='*/1'),  # Запускать каждую минуту
    },
}

# Автоматически находим и регистрируем задачи (tasks.py) в приложениях Django
app.autodiscover_tasks()