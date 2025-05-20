from celery import shared_task
from django.utils import timezone
from .models import Event
from datetime import timedelta
from bot_app.telegram_bot import bot
from pytz import timezone as pytz_timezone
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

@shared_task
def update_recurring_events():
    """Обновление дат повторяющихся событий"""
    now = timezone.now()
    recurring_events = Event.objects.filter(
        recurrence__in=['daily', 'weekly', 'monthly'],
        date__lt=now  # Только прошедшие события
    )
    print(recurring_events)
    for event in recurring_events:
        if event.recurrence == 'daily':
            event.date += timedelta(days=1)
        elif event.recurrence == 'weekly':
            event.date += timedelta(weeks=1)
        elif event.recurrence == 'monthly':
            # Переносим на тот же день следующего месяца
            next_month = event.date.month + 1
            year = event.date.year
            if next_month > 12:
                next_month = 1
                year += 1
            event.date = event.date.replace(month=next_month, year=year)
        
        event.save()

@shared_task
def send_event_reminders():
    """Отправка уведомлений за час до события"""
    now = timezone.now()
    reminder_time = now + timedelta(hours=1)

    upcoming_events = Event.objects.filter(
        date__gte=now,
        date__lte=reminder_time,
        reminder_sent=False
    )

    moscow = pytz_timezone('Europe/Moscow')

    for event in upcoming_events:
        event_time_msk = event.date.astimezone(moscow).strftime('%H:%M')
        for group in event.groups.all():
            for student in group.student_set.all():
                if student.user.telegram_id:
                    message = (
                        "⏰ Напоминание о событии:\n"
                        f"Название: {event.title}\n"
                        f"Начало через 1 час ({event_time_msk})\n"
                        f"Описание: {event.description}"
                    )
                    bot.send_message(student.user.telegram_id, message)
                    event.reminder_sent = True
                    event.save()

@shared_task
def delete_old_submissions():
    """Удаляет файлы и записи, старше 30 дней"""
    threshold = timezone.now() - timedelta(days=30)
    old_subs = StudentSubmission.objects.filter(created_at__lt=threshold)

    for sub in old_subs:
        if sub.file and os.path.exists(sub.file.path):
            try:
                os.remove(sub.file.path)
            except Exception as e:
                print(f"Не удалось удалить файл: {sub.file.path} — {e}")
    old_subs.delete()