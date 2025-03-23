from telebot import TeleBot, types
import logging
import os
import requests
from django.core.cache import cache
import os
import django
from django.utils.timezone import now
from django.conf import settings
from datetime import datetime
from bot_app.oauth import set_user_state, get_user_state

# Указываем путь к настройкам Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bauman_event_tg_bot.settings')
django.setup()

from .models import User, Student, Teacher, Group, Event
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = '7537310088:AAEfsIy_njqdYZ8bDBRcyz4i7doWXp6dQB8'
bot = TeleBot(TOKEN)

API_URL = "https://science.iu5.bmstu.ru/sso/authorize?redirect_uri=http://127.0.0.1:8000/oauth_callback"  # Адрес вашего Django приложения


# Установка всплывающего меню команд
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Авторизация через университет"),
        types.BotCommand("create_event", "Создать событие"),
        types.BotCommand("events", "Посмотреть список событий"),
    ]
    bot.set_my_commands(commands)


@bot.message_handler(commands=['start'])
def start(message):
    telegram_id = message.chat.id
    logger.info(f"Получена команда /start от пользователя {telegram_id}")

    # Сохраняем telegram_id в Redis с уникальным ключом
    session_key = f"tgid_{telegram_id}"
    cache.set(session_key, telegram_id, timeout=300)  # Храним 5 минут

    # Формируем state с telegram_id
    tg = f"telegram_id={telegram_id}"

    # Отправляем ссылку с state
    auth_url = f"{API_URL}?tg={tg}"
    bot.send_message(
        telegram_id,
        "Привет! Авторизуйтесь через сайт университета.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Авторизация", url=auth_url)
        )
    )

@bot.message_handler(func=lambda message: message.text in ['Да', 'Нет'])
def handle_teacher_response(message):
    telegram_id = message.chat.id
    response = message.text

    # Проверяем, ожидает ли бот ответа на вопрос о преподавателе
    if get_user_state(telegram_id) != "awaiting_teacher_response":
        return  # Игнорируем сообщение, если состояние не соответствует

    try:
        # Получаем пользователя из базы данных по telegram_id
        user = User.objects.get(telegram_id=telegram_id)

        if response == 'Да':
            # Пользователь - преподаватель
            teacher, created = Teacher.objects.get_or_create(user=user)
            bot.send_message(telegram_id, "Вы зарегистрированы как преподаватель.")
        else:
            # Пользователь - студент, запросим группу
            bot.send_message(telegram_id, "Введите номер вашей группы:")
            bot.register_next_step_handler(message, handle_group_input, user)

        # Очищаем состояние пользователя после обработки ответа
        set_user_state(telegram_id, None)

    except User.DoesNotExist:
        bot.send_message(telegram_id, "Ошибка: пользователь не найден.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка: {str(e)}")

def handle_group_input(message, user):
    telegram_id = message.chat.id
    group_name = message.text

    try:
        # Создаем группу, если ее нет
        group, created = Group.objects.get_or_create(name=group_name)

        # Создаем запись студента
        student, created = Student.objects.get_or_create(user=user)
        student.group = group
        student.save()
        bot.send_message(telegram_id, f"Вы зарегистрированы как студент группы {group_name}.")

    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка при обработке данных: {str(e)}")

@bot.message_handler(commands=['отмена', 'cancel'])
def handle_cancel(message):
    telegram_id = message.chat.id

    # Очищаем временные данные
    if telegram_id in event_data:
        del event_data[telegram_id]

    bot.send_message(telegram_id, "Создание события отменено.")

# Временное хранилище для данных о событии
event_data = {}

@bot.message_handler(commands=['create_event'])
def handle_create_event(message):
    """Обработчик команды /create_event"""
    telegram_id = message.chat.id

    # Проверяем, является ли пользователь преподавателем
    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)
    except (User.DoesNotExist, Teacher.DoesNotExist):
        bot.send_message(telegram_id, "Только преподаватели могут создавать события.")
        return

    # Запрашиваем название события
    bot.send_message(telegram_id, "Введите название события (или введите 'Отмена' для отмены):")
    bot.register_next_step_handler(message, process_title_step)

def process_title_step(message):
    """Обработка названия события"""
    telegram_id = message.chat.id

    # Если пользователь ввел команду "Отмена"
    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    event_data[telegram_id] = {'title': message.text}

    # Запрашиваем описание события
    bot.send_message(telegram_id, "Введите описание события (или введите 'Отмена' для отмены):")
    bot.register_next_step_handler(message, process_description_step)

def process_description_step(message):
    """Обработка описания события"""
    telegram_id = message.chat.id

    # Если пользователь ввел команду "Отмена"
    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    event_data[telegram_id]['description'] = message.text

    # Запрашиваем дату события
    bot.send_message(telegram_id, "Введите дату события в формате ГГГГ-ММ-ДД ЧЧ:ММ (или введите 'Отмена' для отмены):")
    bot.register_next_step_handler(message, process_date_step)

def process_date_step(message):
    """Обработка даты события"""
    telegram_id = message.chat.id

    # Если пользователь ввел команду "Отмена"
    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    try:
        # Пытаемся преобразовать введенный текст в дату
        event_data[telegram_id]['date'] = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        
        # Если дата введена корректно, переходим к следующему шагу
        groups = Group.objects.all()
        if not groups:
            bot.send_message(telegram_id, "Нет доступных групп.")
            return

        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for group in groups:
            markup.add(types.KeyboardButton(group.name))
        bot.send_message(telegram_id, "Выберите группы (введите через запятую):", reply_markup=markup)
        bot.register_next_step_handler(message, process_groups_step)
    except ValueError:
        # Если дата введена некорректно, запрашиваем повторный ввод
        bot.send_message(telegram_id, "Неверный формат даты. Попробуйте снова (введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ):")
        bot.register_next_step_handler(message, process_date_step)  # Повторно вызываем эту же функцию

def process_groups_step(message):
    """Обработка выбора групп"""
    telegram_id = message.chat.id

    # Если пользователь ввел команду "Отмена"
    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    selected_groups = message.text.split(', ')
    event_data[telegram_id]['groups'] = Group.objects.filter(name__in=selected_groups)

    # Запрашиваем тип повторения
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add('Без повторения', 'Ежедневно', 'Еженедельно', 'Ежемесячно')
    bot.send_message(telegram_id, "Выберите тип повторения:", reply_markup=markup)
    bot.register_next_step_handler(message, process_recurrence_step)

def process_recurrence_step(message):
    """Обработка типа повторения"""
    telegram_id = message.chat.id

    # Если пользователь ввел команду "Отмена"
    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    # Сохраняем тип повторения
    recurrence_mapping = {
        'Без повторения': 'none',
        'Ежедневно': 'daily',
        'Еженедельно': 'weekly',
        'Ежемесячно': 'monthly',
    }
    event_data[telegram_id]['recurrence'] = recurrence_mapping.get(message.text, 'none')

    # Запрашиваем файл
    bot.send_message(telegram_id, "Приложите файл (если необходимо, или введите 'Пропустить'):")
    bot.register_next_step_handler(message, process_file_step)


def process_file_step(message):
    """Обработка файла"""
    telegram_id = message.chat.id

    # Если пользователь ввел команду "Отмена"
    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    if message.document:
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = message.document.file_name

        # Создаем директорию, если она не существует
        os.makedirs(os.path.join(settings.MEDIA_ROOT, 'event_files'), exist_ok=True)

        file_path = os.path.join(settings.MEDIA_ROOT, 'event_files', file_name)
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        event_data[telegram_id]['file'] = file_path
    else:
        event_data[telegram_id]['file'] = None

    # Создаем событие
    create_event_from_data(telegram_id)

def create_event_from_data(telegram_id):
    """Создание события на основе собранных данных"""
    data = event_data.get(telegram_id)
    if not data:
        bot.send_message(telegram_id, "Ошибка: данные не найдены.")
        return

    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)

        # Создаем событие
        event = Event.objects.create(
            title=data['title'],
            description=data['description'],
            date=data['date'],
            teacher=teacher,
            file=data['file'],
            recurrence=data.get('recurrence', 'none')  # Добавляем поле повторения
        )
        # Связываем группы с событием
        event.groups.set(data['groups'])

        # Отправляем уведомления ученикам
        for group in data['groups']:
            students = Student.objects.filter(group=group)
            for student in students:
                if student.user.telegram_id:
                    # Формируем сообщение
                    recurrence_info = get_recurrence_info(event)  # Получаем информацию о повторении
                    message = (
                        f"Новое событие:\n"
                        f"Название: {event.title}\n"
                        f"Описание: {event.description}\n"
                        f"Дата: {event.date}\n"
                        f"Повторение: {recurrence_info}\n"  # Добавляем информацию о повторении
                    )
                    # Отправляем сообщение
                    bot.send_message(student.user.telegram_id, message)
                    # Если есть файл, отправляем его
                    if event.file:
                        with open(event.file.path, 'rb') as file:
                            bot.send_document(student.user.telegram_id, file)

        bot.send_message(telegram_id, "Событие успешно создано и уведомления отправлены.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка при создании события: {str(e)}")
    finally:
        # Очищаем временные данные
        if telegram_id in event_data:
            del event_data[telegram_id]


@bot.message_handler(commands=['events'])
def handle_events(message):
    """Обработчик команды /events"""
    telegram_id = message.chat.id

    try:
        # Получаем пользователя
        user = User.objects.get(telegram_id=telegram_id)

        # Проверяем, является ли пользователь студентом
        try:
            student = Student.objects.get(user=user)
            # Если студент, получаем события для его группы
            events = Event.objects.filter(groups=student.group)
            if events:
                response = "Ваши события:\n"
                for event in events:
                    recurrence_info = get_recurrence_info(event)  # Получаем информацию о повторении
                    response += (
                        f"Название: {event.title}\n"
                        f"Описание: {event.description}\n"
                        f"Дата: {event.date}\n"
                        f"Повторение: {recurrence_info}\n"  # Добавляем информацию о повторении
                        f"Преподаватель: {event.teacher.user.username}\n\n"
                    )
            else:
                response = "У вас нет предстоящих событий."
        except Student.DoesNotExist:
            # Если не студент, проверяем, является ли пользователь преподавателем
            try:
                teacher = Teacher.objects.get(user=user)
                # Если преподаватель, получаем созданные им события
                events = Event.objects.filter(teacher=teacher)
                if events:
                    response = "Ваши созданные события:\n"
                    for event in events:
                        recurrence_info = get_recurrence_info(event)  # Получаем информацию о повторении
                        response += (
                            f"Название: {event.title}\n"
                            f"Описание: {event.description}\n"
                            f"Дата: {event.date}\n"
                            f"Повторение: {recurrence_info}\n"  # Добавляем информацию о повторении
                            f"Группы: {', '.join([group.name for group in event.groups.all()])}\n\n"
                        )
                else:
                    response = "Вы еще не создали ни одного события."
            except Teacher.DoesNotExist:
                response = "Вы не являетесь ни студентом, ни преподавателем."

        # Отправляем ответ пользователю
        bot.send_message(telegram_id, response)
    except User.DoesNotExist:
        bot.send_message(telegram_id, "Пользователь не найден.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка: {str(e)}")

def get_recurrence_info(event):
    """Возвращает текстовое описание повторения события"""
    if event.recurrence == 'none':
        return "Без повторения"
    elif event.recurrence == 'daily':
        return "Ежедневно"
    elif event.recurrence == 'weekly':
        return "Еженедельно"
    elif event.recurrence == 'monthly':
        return "Ежемесячно"
    else:
        return "Неизвестно"

# Запуск бота
def start_bot():
    # Устанавливаем команды
    set_bot_commands()

    # Проверяем, что это основной процесс
    if os.environ.get('RUN_MAIN') != 'true':
        print("Бот запущен!")
        bot.polling(none_stop=True)
