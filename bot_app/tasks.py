from celery import shared_task
from django.utils import timezone
from .models import Event

@shared_task
def delete_past_non_recurring_events():
    """Удаляет неповторяющиеся события, которые уже прошли"""
    try:
        print("Задача по удалению событий запущена.")
        past_events = Event.objects.filter(date__lt=timezone.now(), recurrence='none')
        print(f"Найдено {past_events.count()} событий для удаления.")
        past_events.delete()
        print("События успешно удалены.")
    except Exception as e:
        print(f"Ошибка при удалении событий: {e}")