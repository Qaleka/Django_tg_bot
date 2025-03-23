import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from bot_app.models import User
from django.db.models import Q
from .models import Student, Event, Group
from django.utils.timezone import now
from django.core.cache import cache
from django.shortcuts import redirect
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from bot_app.oauth import clear_session, get_current_user, auth_token
from rest_framework.renderers import TemplateHTMLRenderer
from telebot import TeleBot, types
from django.core.files.storage import default_storage
from bot_app.oauth import set_user_state
TOKEN = '7537310088:AAEfsIy_njqdYZ8bDBRcyz4i7doWXp6dQB8'
bot = TeleBot(TOKEN)

@api_view(['GET'])
def oauth_callback(request):
    clear_session(request)

    # Получаем код авторизации и state
    code = request.GET.get('code', '')
    tg = request.GET.get('tg', '')
    print(tg)
    # Извлекаем telegram_id из state
    telegram_id = None
    if tg:
        state_params = tg.split('&')
        for param in state_params:
            if param.startswith('telegram_id='):
                telegram_id = param.split('=')[1]
                break

    if not telegram_id:
        return Response({'message': 'Telegram ID not found'}, status=400)

    # Сохраняем telegram_id в Redis
    session_key = f"session_{request.session.session_key}"
    cache.set(f"{session_key}_telegram_id", telegram_id, timeout=3600)

    try:
        token = auth_token(request)
        cache.set(f"{session_key}_token", token, timeout=3600)
    except Exception as e:
        return Response({'message': 'Failed to fetch token', 'error': str(e)}, status=400)

    user = get_current_user(request)

    if user:
        # Достаем telegram_id из Redis
        telegram_id = cache.get(f"{session_key}_telegram_id")

        if not telegram_id:
            return Response({'message': 'Telegram ID not found'}, status=400)

        cache.set(f"{session_key}_user", user, timeout=3600)

        # Проверяем, есть ли пользователь с таким telegram_id в базе данных
        try:
            django_user = User.objects.get(telegram_id=telegram_id)
            # Перенаправляем на страницу успешной авторизации с сообщением
            url = f"/auth_success?telegram_id={telegram_id}&message=Вы уже авторизованы.&"
            for field, value in user.items():
                url += f"{field}={value}&"
            return redirect(url.rstrip('&'))
        except User.DoesNotExist:
            # Если пользователь не найден, создаем новую запись
            django_user, created = User.objects.get_or_create(
                username=user["username"],
                defaults={
                    "firstname": user.get("firstname", ""),
                    "secondName": user.get("lastname", ""),
                    "telegram_id": telegram_id,
                }
            )
            print("Успех")
            message = "Пользователь успешно зарегистрирован."

        # Очистка временного ключа в Redis
        cache.delete(f"{session_key}_telegram_id")

        url = f"/auth_success?telegram_id={telegram_id}&message={message}&"
        for field, value in user.items():
            url += f"{field}={value}&"
        return redirect(url.rstrip('&'))

# Обработчик для получения списка событий для студента
def student_events(request):
    user_id = request.user.id
    try:
        student = Student.objects.get(user_id=user_id)
        events = Event.objects.filter(groups=student.group, date__gte=now())

        events_data = [
            {
                "title": event.title,
                "description": event.description,
                "date": event.date
            } for event in events
        ]
        return JsonResponse({"events": events_data})
    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)
    
@api_view(['GET'])
@renderer_classes([TemplateHTMLRenderer])
def auth_success(request):
    telegram_id = request.query_params.get('telegram_id', '')
    message = request.query_params.get('message', '')

    if telegram_id:
        # Отправляем сообщение в Telegram
        bot.send_message(telegram_id, message)

        # Если пользователь уже авторизован, не задаем вопрос про учителя и группу
        if "уже авторизован" not in message:
            # Устанавливаем состояние пользователя
            set_user_state(telegram_id, "awaiting_teacher_response")

            # Далее можно задать вопрос о том, является ли пользователь учителем
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
            markup.add('Да', 'Нет')
            bot.send_message(telegram_id, "Вы преподаватель?", reply_markup=markup)

    data = {
        'status': 'ok',
        'message': message,
    }

    return render(request, 'success_page.html', {'data': data})