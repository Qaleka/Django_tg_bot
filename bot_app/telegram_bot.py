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
from pytz import timezone, utc
from pytz import timezone as pytz_timezone
from dotenv import load_dotenv
from datetime import timedelta

MOSCOW_TZ = timezone('Europe/Moscow')
# Указываем путь к настройкам Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bauman_event_tg_bot.settings')
django.setup()
load_dotenv()  # загружает переменные из .env
from .models import User, Student, Teacher, Group, Event, StudentSubmission
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = TeleBot(TOKEN)

API_URL = "https://science.iu5.bmstu.ru/sso/authorize?redirect_uri=https://baumeventbot.ru/oauth_callback"  # Адрес вашего Django приложения

def require_auth(handler_func):
    """Декоратор для проверки авторизации"""
    def wrapper(message, *args, **kwargs):
        telegram_id = message.chat.id
        if not User.objects.filter(telegram_id=telegram_id).exists():
            auth_url = f"{API_URL}?tg=telegram_id={telegram_id}"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Авторизоваться", url=auth_url))
            bot.send_message(
                telegram_id,
                "❗ Вы не авторизованы. Пожалуйста, авторизуйтесь через сайт университета.",
                reply_markup=markup
            )
            return
        return handler_func(message, *args, **kwargs)
    return wrapper


# Установка всплывающего меню команд
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Авторизация через университет"),
        types.BotCommand("calendar", "Открыть календарь событий"),
        types.BotCommand("create_event", "Создать новое событие"),
        types.BotCommand("events", "Список всех событий"),
        types.BotCommand("delete_event", "Удалить событие (для преподавателей)"),
        types.BotCommand("send_file", "Отправить файл преподавателю"),
        types.BotCommand("received_files", "Полученные файлы за месяц")
    ]
    bot.set_my_commands(commands)


@bot.message_handler(commands=['start'])
def start(message):
    # Очищаем состояние пользователя
    set_user_state(message.chat.id, None)
    
    # Удаляем предыдущие кнопки (если есть)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(
        message.chat.id,
        "Привет! Авторизуйтесь через сайт университета.",
        reply_markup=types.ReplyKeyboardRemove()  # Удаляем все кнопки
    )
    
    # Создаем ссылку для авторизации
    auth_url = f"{API_URL}?tg=telegram_id={message.chat.id}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Авторизация", url=auth_url))
    
    bot.send_message(
        message.chat.id,
        "Нажмите кнопку ниже для авторизации:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text in ['Да', 'Нет'])
@require_auth
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
@require_auth
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
    telegram_id = message.chat.id

    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    try:
        # пользователь вводит московское время, без зоны
        naive_dt = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        moscow = timezone("Europe/Moscow")
        aware_dt = moscow.localize(naive_dt)  # делаем aware datetime
        event_data[telegram_id]['date'] = aware_dt  # Django сам сохранит в UTC

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
        bot.send_message(telegram_id, "Неверный формат даты. Попробуйте снова (введите дату в формате ГГГГ-ММ-ДД ЧЧ:ММ):")
        bot.register_next_step_handler(message, process_date_step)

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
                        f"Преподаватель:{event.teacher.user.secondName} {event.teacher.user.firstname} {event.teacher.user.middlename}\n"
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
@require_auth
def handle_events(message):
    """Обработчик команды /events"""
    msk = pytz_timezone("Europe/Moscow")
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
                        f"Дата: {event.date.astimezone(msk).strftime('%Y-%m-%d %H:%M')}\n"
                        f"Повторение: {recurrence_info}\n"  # Добавляем информацию о повторении
                        f"Преподаватель: {event.teacher.user.secondName} {event.teacher.user.firstname} {event.teacher.user.middlename}\n\n"
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

@bot.message_handler(commands=['calendar'])
@require_auth
def handle_calendar(message):
    webapp_url = f"https://baumeventbot.ru/calendar/?tgid={message.chat.id}"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "📅 Открыть календарь", 
        web_app=types.WebAppInfo(url=webapp_url)
    ))
    
    bot.send_message(
        message.chat.id,
        "Нажмите кнопку для открытия календаря (не забудьте разрешить небезопасные соединения в Telegram):",
        reply_markup=markup
    )

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

@bot.message_handler(commands=['delete_event'])
@require_auth
def handle_delete_event(message):
    """Обработчик удаления событий (только для преподавателей)"""
    telegram_id = message.chat.id
    
    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)
        
        # Получаем все события преподавателя
        events = Event.objects.filter(teacher=teacher)
        
        if not events:
            bot.send_message(telegram_id, "У вас нет событий для удаления.")
            return
            
        # Создаем клавиатуру с событиями
        markup = types.InlineKeyboardMarkup()
        for event in events:
            markup.add(types.InlineKeyboardButton(
                f"{event.title} ({event.date.strftime('%d.%m.%Y')})",
                callback_data=f"delete_event_{event.id}"
            ))
            
        bot.send_message(
            telegram_id,
            "Выберите событие для удаления:",
            reply_markup=markup
        )
        
    except Teacher.DoesNotExist:
        bot.send_message(telegram_id, "Эта команда доступна только преподавателям.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_event_'))
def confirm_deletion(call):
    """Подтверждение удаления и отправка уведомлений"""
    try:
        event_id = int(call.data.split('_')[2])
        event = Event.objects.get(id=event_id)
        
        # Создаем клавиатуру подтверждения
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{event.id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Вы уверены, что хотите удалить событие '{event.title}'?",
            reply_markup=markup
        )
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_'))
def delete_event_and_notify(call):
    """Удаление события и рассылка уведомлений"""
    try:
        event_id = int(call.data.split('_')[2])
        event = Event.objects.get(id=event_id)
        event_title = event.title
        groups = list(event.groups.all())  # Сохраняем группы перед удалением
        
        # Удаляем событие
        event.delete()
        
        # Уведомляем преподавателя
        bot.answer_callback_query(call.id, "Событие удалено")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Событие '{event_title}' успешно удалено."
        )
        
        # Рассылаем уведомления участникам
        for group in groups:
            for student in group.student_set.all():
                if student.user.telegram_id:
                    try:
                        bot.send_message(
                            student.user.telegram_id,
                            f"❌ Событие отменено:\n{event_title}\n"
                            f"Дата: {event.date.strftime('%d.%m.%Y %H:%M')}\n"
                            f"Преподаватель: {event.teacher.user.username}"
                        )
                    except Exception as e:
                        logging.error(f"Не удалось уведомить {student.user.telegram_id}: {str(e)}")
                        
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка при удалении: {str(e)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
def cancel_deletion(call):
    """Отмена удаления события"""
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Удаление отменено."
    )

submission_data = {}

@bot.message_handler(commands=['send_file'])
@require_auth
def initiate_submission(message):
    telegram_id = message.chat.id
    try:
        user = User.objects.get(telegram_id=telegram_id)
        student = Student.objects.get(user=user)
    except (User.DoesNotExist, Student.DoesNotExist):
        bot.send_message(telegram_id, "Эта команда доступна только студентам.")
        return

    # Выбор преподавателя
    teachers = Teacher.objects.all()
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for t in teachers:
        full_name = f"{t.user.secondName} {t.user.firstname[0]}.{t.user.middlename[0]}."
        markup.add(types.KeyboardButton(full_name))

    bot.send_message(telegram_id, "Выберите преподавателя:", reply_markup=markup)

    bot.register_next_step_handler(message, handle_teacher_selection)

def handle_teacher_selection(message):
    telegram_id = message.chat.id
    input_text = message.text.strip()

    selected_teacher = None
    for teacher in Teacher.objects.select_related('user').all():
        firstname = teacher.user.firstname or ""
        secondname = teacher.user.secondName or ""
        middlename = teacher.user.middlename or ""
        full_name = f"{secondname} {firstname[0]}.{middlename[0]}."
        if full_name == input_text:
            selected_teacher = teacher
            break

    if not selected_teacher:
        bot.send_message(telegram_id, "Преподаватель не найден. Попробуйте снова.")
        initiate_submission(message)
        return

    # Сохраняем выбранного преподавателя
    submission_data[telegram_id] = {'teacher': selected_teacher}

    bot.send_message(telegram_id, "Введите описание файла:")
    bot.register_next_step_handler(message, handle_description_input)

def handle_description_input(message):
    telegram_id = message.chat.id
    submission_data[telegram_id]['description'] = message.text
    bot.send_message(telegram_id, "Прикрепите файл:")
    bot.register_next_step_handler(message, handle_file_upload)

def handle_file_upload(message):
    telegram_id = message.chat.id

    if not message.document:
        bot.send_message(telegram_id, "Пожалуйста, отправьте документ.")
        bot.register_next_step_handler(message, handle_file_upload)
        return

    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    file_data = bot.download_file(file_info.file_path)
    file_name = message.document.file_name

    file_path = os.path.join(settings.MEDIA_ROOT, 'submissions', file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb') as f:
        f.write(file_data)

    submission_data[telegram_id]['file_path'] = file_path
    submission_data[telegram_id]['file_name'] = file_name

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Отправить", callback_data="confirm_submission"))
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_submission"))
    bot.send_message(telegram_id, "Подтвердите отправку файла:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_submission", "cancel_submission"])
def handle_submission_confirmation(call):
    telegram_id = call.message.chat.id
    data = submission_data.get(telegram_id)

    if call.data == "cancel_submission":
        submission_data.pop(telegram_id, None)
        bot.edit_message_text("Отправка отменена.", telegram_id, call.message.message_id)
        return

    if data:
        user = User.objects.get(telegram_id=telegram_id)
        student = Student.objects.get(user=user)

        submission = StudentSubmission.objects.create(
            student=student,
            teacher=data['teacher'],
            description=data['description'],
        )
        submission.file.name = f"submissions/{os.path.basename(data['file_path'])}"
        submission.save()

        # Уведомим преподавателя
        if data['teacher'].user.telegram_id:
            bot.send_message(
                data['teacher'].user.telegram_id,
                f"📥 Новый файл от {student.user.secondName} {student.user.firstname} {student.user.middlename}:\nОписание: {data['description']}"
            )
            with open(data['file_path'], 'rb') as f:
                bot.send_document(data['teacher'].user.telegram_id, f)

        bot.edit_message_text("Файл успешно отправлен!", telegram_id, call.message.message_id)
        submission_data.pop(telegram_id, None)

@bot.message_handler(commands=['received_files'])
@require_auth
def view_received_files(message):
    telegram_id = message.chat.id
    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)
    except (User.DoesNotExist, Teacher.DoesNotExist):
        bot.send_message(telegram_id, "Только преподаватели могут просматривать полученные файлы.")
        return

    cutoff = now() - timedelta(days=30)

    submissions = StudentSubmission.objects.filter(teacher=teacher, created_at__gte=cutoff).order_by('-created_at')

    if not submissions.exists():
        bot.send_message(telegram_id, "За последний месяц нет новых отправок.")
        return

    for sub in submissions:
        local_dt = sub.created_at.astimezone(MOSCOW_TZ)
        text = (
            f"👤 Студент: {sub.student.user.secondName} {sub.student.user.firstname} {sub.student.user.middlename}\n"
            f"📝 Описание: {sub.description}\n"
            f"📅 Дата: {local_dt.strftime('%d.%m.%Y %H:%M')}"
        )
        try:
            bot.send_message(telegram_id, text)
            if sub.file:
                with open(sub.file.path, 'rb') as f:
                    bot.send_document(telegram_id, f)
        except Exception as e:
            bot.send_message(telegram_id, f"Ошибка при отправке файла: {str(e)}")


# Запуск бота
def start_bot():
    set_bot_commands()
    
    # Проверяем, что это основной процесс (не reloader)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or os.environ.get('RUN_MAIN') == 'true':
        print("Бот запущен!")
        try:
            bot.polling(none_stop=True, skip_pending=True)
        except Exception as e:
            print(f"Ошибка в работе бота: {e}")

import atexit

def stop_bot():
    try:
        bot.stop_polling()  # Просто пытаемся остановить, без проверки running
    except Exception as e:
        print(f"Ошибка при остановке бота: {e}")

atexit.register(stop_bot)