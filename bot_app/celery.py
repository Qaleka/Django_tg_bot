import os
from celery import Celery
from django.conf import settings
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bauman_event_tg_bot.settings')

app = Celery('bot_app')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.beat_schedule = {
    'delete-past-events': {
        'task': 'bot_app.tasks.delete_past_non_recurring_events',
        'schedule': crontab(minute='*/1'),  # Запускать каждую минуту
    },
    'update-recurring-events': {
        'task': 'bot_app.tasks.update_recurring_events',
        'schedule': crontab(minute='*/1'),  # Каждый день в 00:00
    },
    'send-reminders': {
        'task': 'bot_app.tasks.send_event_reminders',
        'schedule': crontab(minute='*/1'),  # Каждые 5 минут
    },
    'delete-old-submissions': {
        'task': 'bot_app.tasks.delete_old_submissions',
        'schedule': crontab(hour=0, minute=0),  # каждый день в полночь
    },
}

app.autodiscover_tasks()