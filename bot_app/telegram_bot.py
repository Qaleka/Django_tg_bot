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
from datetime import datetime, timedelta
from functools import lru_cache

MOSCOW_TZ = timezone('Europe/Moscow')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bauman_event_tg_bot.settings')
django.setup()
load_dotenv()  # загружает переменные из .env
from .models import User, Student, Teacher, Group, Event, StudentSubmission, EventResponse
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = TeleBot(TOKEN)
BACKEND_URL = "https://baumeventbot.ru"

API_URL = f"https://science.iu5.bmstu.ru/sso/authorize?redirect_uri={BACKEND_URL}/oauth_callback"

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
        types.BotCommand("received_files", "Полученные файлы за месяц"),
        types.BotCommand("responses", "Посмотреть статус студентов по событиям"),
        types.BotCommand("edit_event", "Отредактировать событие")
    ]
    bot.set_my_commands(commands)


@bot.message_handler(commands=['start'])
def start(message):
    set_user_state(message.chat.id, None)
    
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(
        message.chat.id,
        "Привет! Авторизуйтесь через сайт университета.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
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

    if get_user_state(telegram_id) != "awaiting_teacher_response":
        return

    try:
        # Получаем пользователя из базы данных по telegram_id
        user = User.objects.get(telegram_id=telegram_id)

        if response == 'Да':
            teacher, created = Teacher.objects.get_or_create(user=user)
            bot.send_message(telegram_id, "Вы зарегистрированы как преподаватель.")
        else:
            bot.send_message(telegram_id, "Введите номер вашей группы:")
            bot.register_next_step_handler(message, handle_group_input, user)

        set_user_state(telegram_id, None)

    except User.DoesNotExist:
        bot.send_message(telegram_id, "Ошибка: пользователь не найден.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка: {str(e)}")

@lru_cache
def get_valid_groups():
    with open("extracted_groups.txt", "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def handle_group_input(message, user):
    telegram_id = message.chat.id
    group_name = message.text.strip()

    valid_groups = get_valid_groups()

    if group_name not in valid_groups:
        bot.send_message(telegram_id, "Такой группы не найдено. Пожалуйста, введите ещё раз:")
        bot.register_next_step_handler(message, handle_group_input, user)
        return

    try:
        # Проверка: есть ли такая группа в БД
        group, _ = Group.objects.get_or_create(name=group_name)

        # Привязка студента
        student, _ = Student.objects.get_or_create(user=user)
        student.group = group
        student.save()

        bot.send_message(telegram_id, f"Вы зарегистрированы как студент группы {group_name}.")
        set_user_state(telegram_id, None)

    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка при обработке данных: {str(e)}")

@bot.message_handler(commands=['отмена', 'cancel'])
def handle_cancel(message):
    telegram_id = message.chat.id

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

    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)
    except (User.DoesNotExist, Teacher.DoesNotExist):
        bot.send_message(telegram_id, "Только преподаватели могут создавать события.")
        return

    bot.send_message(telegram_id, "Введите название события (или введите 'Отмена' для отмены):")
    bot.register_next_step_handler(message, process_title_step)

def process_title_step(message):
    """Обработка названия события"""
    telegram_id = message.chat.id

    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    event_data[telegram_id] = {'title': message.text}

    bot.send_message(telegram_id, "Введите описание события (или введите 'Отмена' для отмены):")
    bot.register_next_step_handler(message, process_description_step)

def process_description_step(message):
    """Обработка описания события"""
    telegram_id = message.chat.id

    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    event_data[telegram_id]['description'] = message.text

    webapp_url = f"{BACKEND_URL}/select_date/?tgid={telegram_id}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📅 Выбрать дату", web_app=types.WebAppInfo(url=webapp_url)))
    bot.send_message(telegram_id, "Выберите дату и время через календарь:", reply_markup=markup)

    # 👇 Показываем обычную reply-клавиатуру с кнопкой "Готово"
    ready_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    ready_markup.add("Готово")
    bot.send_message(telegram_id, "После выбора даты нажмите «Готово»", reply_markup=ready_markup)


@bot.message_handler(func=lambda message: message.text.lower() == "готово")
def handle_ready_after_webapp(message):
    telegram_id = message.chat.id
    from django.core.cache import cache

    date_str = cache.get(f"selected_date_{telegram_id}")
    if not date_str:
        bot.send_message(telegram_id, "⏳ Дата ещё не выбрана или не получена. Попробуйте позже.")
        return

    try:
        naive_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        moscow = timezone("Europe/Moscow")
        aware_dt = moscow.localize(naive_dt)
        event_data[telegram_id]['date'] = aware_dt
        bot.send_message(telegram_id, "Дата сохранена ✅", reply_markup=types.ReplyKeyboardRemove())
        groups = Group.objects.all()
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for group in groups:
            markup.add(types.KeyboardButton(group.name))
        bot.send_message(telegram_id, "Выберите группы (введите через запятую):", reply_markup=markup)
        bot.register_next_step_handler(message, process_groups_step)

    except Exception as e:
        bot.send_message(telegram_id, f"❌ Ошибка при обработке даты: {str(e)}")

def process_groups_step(message):
    """Обработка выбора групп"""
    telegram_id = message.chat.id

    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    selected_groups = message.text.split(', ')
    event_data[telegram_id]['groups'] = Group.objects.filter(name__in=selected_groups)

    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add('Без повторения', 'Ежедневно', 'Еженедельно', 'Раз в 2 недели', 'Ежемесячно')
    bot.send_message(telegram_id, "Выберите тип повторения(раз в какое время будет происходить событие):", reply_markup=markup)
    bot.register_next_step_handler(message, process_recurrence_step)

def process_recurrence_step(message):
    """Обработка типа повторения"""
    telegram_id = message.chat.id

    if message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    recurrence_mapping = {
        'Без повторения': 'none',
        'Ежедневно': 'daily',
        'Еженедельно': 'weekly',
        'Раз в 2 недели': 'biweekly',
        'Ежемесячно': 'monthly',
    }
    event_data[telegram_id]['recurrence'] = recurrence_mapping.get(message.text, 'none')

    bot.send_message(telegram_id, "Приложите файл (если необходимо, или введите 'Пропустить'):")
    bot.register_next_step_handler(message, process_file_step)


def process_file_step(message):
    """Обработка файла"""
    telegram_id = message.chat.id

    if message.text and message.text.lower() in ['отмена', 'cancel']:
        handle_cancel(message)
        return

    if message.document:
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = message.document.file_name

        os.makedirs(os.path.join(settings.MEDIA_ROOT, 'event_files'), exist_ok=True)

        file_path = os.path.join(settings.MEDIA_ROOT, 'event_files', file_name)
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        event_data[telegram_id]['file'] = file_path
    else:
        event_data[telegram_id]['file'] = None

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

        event = Event.objects.create(
            title=data['title'],
            description=data['description'],
            date=data['date'],
            teacher=teacher,
            file=data['file'],
            recurrence=data.get('recurrence', 'none')
        )

        event.groups.set(data['groups'])

        for group in data['groups']:
            students = Student.objects.filter(group=group)
            for student in students:
                if student.user.telegram_id:
                    recurrence_info = get_recurrence_info(event)
                    message = (
                        f"Новое событие:\n"
                        f"Название: {event.title}\n"
                        f"Описание: {event.description}\n"
                        f"Дата: {event.date}\n"
                        f"Повторение: {recurrence_info}\n"
                        f"Преподаватель:{event.teacher.user.secondName} {event.teacher.user.firstname} {event.teacher.user.middlename}\n"
                    )
                    EventResponse.objects.get_or_create(event=event, student=student, defaults={'response': 'pending'})
                    bot.send_message(student.user.telegram_id, message)
                    if event.file:
                        with open(event.file.path, 'rb') as file:
                            bot.send_document(student.user.telegram_id, file)
                    markup = types.InlineKeyboardMarkup()
                    markup.add(
                        types.InlineKeyboardButton("✅ Приду", callback_data=f"event_yes_{event.id}"),
                        types.InlineKeyboardButton("❌ Не приду", callback_data=f"event_no_{event.id}")
                    )
                    bot.send_message(student.user.telegram_id, "Вы примете участие?", reply_markup=markup)

        bot.send_message(telegram_id, "Событие успешно создано и уведомления отправлены.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка при создании события: {str(e)}")
    finally:
        if telegram_id in event_data:
            del event_data[telegram_id]


@bot.message_handler(commands=['events'])
@require_auth
def handle_events(message):
    """Обработчик команды /events"""
    msk = pytz_timezone("Europe/Moscow")
    telegram_id = message.chat.id

    try:
        user = User.objects.get(telegram_id=telegram_id)

        try:
            student = Student.objects.get(user=user)
            declined_ids = set(
                student.eventresponse_set.filter(response='no').values_list('event_id', flat=True)
            )
            events = Event.objects.filter(groups=student.group).exclude(id__in=declined_ids)
            if events:
                response = "Ваши события:\n"
                for event in events:
                    recurrence_info = get_recurrence_info(event)
                    response += (
                        f"Название: {event.title}\n"
                        f"Описание: {event.description}\n"
                        f"Дата: {event.date.astimezone(msk).strftime('%Y-%m-%d %H:%M')}\n"
                        f"Повторение: {recurrence_info}\n"
                        f"Преподаватель: {event.teacher.user.secondName} {event.teacher.user.firstname} {event.teacher.user.middlename}\n\n"
                    )
            else:
                response = "У вас нет предстоящих событий."
        except Student.DoesNotExist:
            try:
                teacher = Teacher.objects.get(user=user)
                events = Event.objects.filter(teacher=teacher)
                if events:
                    response = "Ваши созданные события:\n"
                    for event in events:
                        recurrence_info = get_recurrence_info(event)
                        response += (
                            f"Название: {event.title}\n"
                            f"Описание: {event.description}\n"
                            f"Дата: {event.date.astimezone(msk).strftime('%Y-%m-%d %H:%M')}\n"
                            f"Повторение: {recurrence_info}\n"
                            f"Группы: {', '.join([group.name for group in event.groups.all()])}\n\n"
                        )
                else:
                    response = "Вы еще не создали ни одного события."
            except Teacher.DoesNotExist:
                response = "Вы не являетесь ни студентом, ни преподавателем."

        bot.send_message(telegram_id, response)
    except User.DoesNotExist:
        bot.send_message(telegram_id, "Пользователь не найден.")
    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка: {str(e)}")

@bot.message_handler(commands=['calendar'])
@require_auth
def handle_calendar(message):
    webapp_url = f"{BACKEND_URL}/calendar/?tgid={message.chat.id}"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "📅 Открыть календарь", 
        web_app=types.WebAppInfo(url=webapp_url)
    ))
    
    bot.send_message(
        message.chat.id,
        "Нажмите кнопку для открытия календаря:",
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
    elif event.recurrence == 'biweekly':
        return "Раз в 2 недели"
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
        
        events = Event.objects.filter(teacher=teacher)
        
        if not events:
            bot.send_message(telegram_id, "У вас нет событий для удаления.")
            return
            
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
        groups = list(event.groups.all())
        
        event.delete()
        
        bot.answer_callback_query(call.id, "Событие удалено")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Событие '{event_title}' успешно удалено."
        )
        
        for group in groups:
            for student in group.student_set.all():
                if student.user.telegram_id:
                    try:
                        bot.send_message(
                            student.user.telegram_id,
                            f"❌ Событие отменено:\n{event_title}\n"
                            f"Дата: {event.date.strftime('%d.%m.%Y %H:%M')}\n"
                            f"Преподаватель: {event.teacher.user.secondName} {event.teacher.user.firstname} {event.teacher.user.middlename}"
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

        if data['teacher'].user.telegram_id:
            text = (
                f"📥 Новый файл от {student.user.get_full_name()}:\n"
                f"📝 Описание: {data['description']}"
            )

            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{submission.id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{submission.id}")
            )

            bot.send_message(data['teacher'].user.telegram_id, text, reply_markup=markup)

        bot.edit_message_text("Файл успешно отправлен!", telegram_id, call.message.message_id)
        submission_data.pop(telegram_id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_") or call.data.startswith("reject_"))
def handle_submission_decision(call):
    action, submission_id = call.data.split('_')
    try:
        submission = StudentSubmission.objects.get(id=submission_id)
        teacher = submission.teacher
        student = submission.student

        if action == "accept":
            submission.status = 'accepted'
            bot.answer_callback_query(call.id, "✅ Работа принята")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(student.user.telegram_id, f"✅ Ваш файл принят преподавателем.")

            # Отправляем файл преподавателю
            if submission.file and os.path.exists(submission.file.path):
                with open(submission.file.path, 'rb') as f:
                    bot.send_document(teacher.user.telegram_id, f)
        else:
            submission.status = 'rejected'
            bot.answer_callback_query(call.id, "❌ Работа отклонена")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(student.user.telegram_id, f"❌ Ваш файл был отклонён преподавателем.")

        submission.save()

    except StudentSubmission.DoesNotExist:
        bot.answer_callback_query(call.id, "⚠️ Отправка не найдена.", show_alert=True)


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

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("📆 За последний месяц", "👤 По студенту")
    bot.send_message(telegram_id, "Выберите способ просмотра:", reply_markup=markup)

    bot.register_next_step_handler(message, handle_received_files_choice, teacher)

def handle_received_files_choice(message, teacher):
    choice = message.text.strip()

    if choice == "📆 За последний месяц":
        show_recent_files(teacher, message.chat.id)
    elif choice == "👤 По студенту":
        bot.send_message(message.chat.id, "Введите фамилию и имя студента:")
        bot.register_next_step_handler(message, handle_specific_student_files, teacher)
    else:
        bot.send_message(message.chat.id, "Неверный выбор. Используйте команду /received_files ещё раз.")

def handle_specific_student_files(message, teacher):
    query = message.text.strip().lower()
    parts = query.split()

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Пожалуйста, введите фамилию и имя. Повторите команду")
        return

    surname, firstname = parts[0], parts[1]

    matches = Student.objects.filter(
        user__secondName__icontains=surname,
        user__firstname__icontains=firstname
    )

    if not matches.exists():
        bot.send_message(message.chat.id, "Студент не найден.")
        return

    if matches.count() == 1:
        student = matches.first()
        show_student_files(message.chat.id, teacher, student)
        return

    # Если несколько — показываем кнопки
    markup = types.InlineKeyboardMarkup()
    for s in matches:
        label = f"{s.user.secondName} {s.user.firstname} ({s.user.username})"
        markup.add(types.InlineKeyboardButton(label, callback_data=f"student_files_{s.id}"))

    bot.send_message(message.chat.id, "Выберите нужного студента:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("student_files_"))
def show_files_for_selected_student(call):
    try:
        student_id = int(call.data.split("_")[2])
        student = Student.objects.get(id=student_id)
        teacher = Teacher.objects.get(user__telegram_id=call.message.chat.id)
        bot.answer_callback_query(call.id)
        show_student_files(call.message.chat.id, teacher, student)
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}", show_alert=True)

def show_student_files(chat_id, teacher, student):
    submissions = StudentSubmission.objects.filter(
        teacher=teacher,
        student=student,
        status='accepted'
    ).order_by('-created_at')

    if not submissions.exists():
        bot.send_message(chat_id, f"📂 У студента {student.user.get_full_name()} нет принятых файлов.")
        return

    for sub in submissions:
        local_dt = sub.created_at.astimezone(MOSCOW_TZ)
        text = (
            f"👤 Студент: {sub.student.user.get_full_name()}\n"
            f"📝 Описание: {sub.description}\n"
            f"📅 Дата: {local_dt.strftime('%d.%m.%Y %H:%M')}"
        )
        bot.send_message(chat_id, text)
        if sub.file:
            with open(sub.file.path, 'rb') as f:
                bot.send_document(chat_id, f)

def show_recent_files(teacher, chat_id):
    cutoff = now() - timedelta(days=30)
    submissions = StudentSubmission.objects.filter(
        teacher=teacher,
        created_at__gte=cutoff,
        status='accepted'  # показываем только принятые
    ).order_by('-created_at')

    if not submissions.exists():
        bot.send_message(chat_id, "Нет новых принятых файлов за последний месяц.")
        return

    for sub in submissions:
        local_dt = sub.created_at.astimezone(MOSCOW_TZ)
        text = (
            f"👤 Студент: {sub.student.user.get_full_name()}\n"
            f"📝 Описание: {sub.description}\n"
            f"📅 Дата: {local_dt.strftime('%d.%m.%Y %H:%M')}"
        )
        bot.send_message(chat_id, text)
        if sub.file:
            with open(sub.file.path, 'rb') as f:
                bot.send_document(chat_id, f)


@bot.callback_query_handler(func=lambda call: call.data.startswith("event_yes_") or call.data.startswith("event_no_"))
def handle_event_response(call):
    try:
        response = 'yes' if call.data.startswith("event_yes_") else 'no'
        event_id = int(call.data.split('_')[-1])
        user = User.objects.get(telegram_id=call.message.chat.id)
        student = Student.objects.get(user=user)
        event = Event.objects.get(id=event_id)

        er, _ = EventResponse.objects.get_or_create(event=event, student=student)
        er.response = response
        er.save()

        status_text = "✅ Вы подтвердили участие." if response == 'yes' else "❌ Вы отказались от участия."

        # Заменим текст сообщения
        updated_text = f"Вы примете участие?\n\n{status_text}"

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=updated_text
        )

        # Убираем "загрузку"
        bot.answer_callback_query(call.id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)


@bot.message_handler(commands=['responses'])
@require_auth
def view_event_responses(message):
    telegram_id = message.chat.id
    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)

        events = Event.objects.filter(teacher=teacher).order_by('-date')
        if not events:
            bot.send_message(telegram_id, "У вас нет событий.")
            return

        markup = types.InlineKeyboardMarkup()
        for e in events:
            markup.add(types.InlineKeyboardButton(
                f"{e.title} ({e.date.strftime('%d.%m.%Y')})",
                callback_data=f"view_responses_{e.id}"
            ))
        bot.send_message(telegram_id, "Выберите событие:", reply_markup=markup)

    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_responses_"))
def show_event_responses(call):
    bot.answer_callback_query(call.id)
    try:
        event_id = int(call.data.split('_')[-1])
        event = Event.objects.get(id=event_id)
        responses = EventResponse.objects.filter(event=event).select_related("student__user")

        yes = [r.student.user.get_full_name() for r in responses if r.response == 'yes']
        no = [r.student.user.get_full_name() for r in responses if r.response == 'no']
        pending = [r.student.user.get_full_name() for r in responses if r.response == 'pending']

        message = (
            f"📅 {event.title} ({event.date.strftime('%d.%m.%Y %H:%M')})\n\n"
            f"✅ Придут:\n" + ("\n".join(yes) or "—") + "\n\n"
            f"❌ Отказались:\n" + ("\n".join(no) or "—") + "\n\n"
            f"❓ Без ответа:\n" + ("\n".join(pending) or "—")
        )
        bot.send_message(call.message.chat.id, message)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.message_handler(commands=['edit_event'])
@require_auth
def handle_edit_event(message):
    telegram_id = message.chat.id
    try:
        user = User.objects.get(telegram_id=telegram_id)
        teacher = Teacher.objects.get(user=user)
    except (User.DoesNotExist, Teacher.DoesNotExist):
        bot.send_message(telegram_id, "Только преподаватели могут редактировать события.")
        return

    events = Event.objects.filter(teacher=teacher).order_by('-date')
    if not events.exists():
        bot.send_message(telegram_id, "У вас нет созданных событий.")
        return

    markup = types.InlineKeyboardMarkup()
    for e in events:
        label = f"{e.title} ({e.date.strftime('%d.%m.%Y %H:%M')})"
        markup.add(types.InlineKeyboardButton(label, callback_data=f"edit_event_{e.id}"))

    bot.send_message(telegram_id, "Выберите событие для редактирования:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_event_"))
def select_event_to_edit(call):
    bot.answer_callback_query(call.id)
    telegram_id = call.message.chat.id
    event_id = int(call.data.split("_")[2])
    try:
        event = Event.objects.get(id=event_id)
        event_data[telegram_id] = {
            'edit': True,
            'event_id': event.id,
            'title': event.title,
            'description': event.description,
            'date': event.date,
            'recurrence': event.recurrence,
            'file': event.file.path if event.file else None
        }

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✏️ Название", callback_data="edit_title"),
            types.InlineKeyboardButton("📄 Описание", callback_data="edit_description"),
        )
        markup.add(
            types.InlineKeyboardButton("🕒 Дата", callback_data="edit_date"),
            types.InlineKeyboardButton("🔁 Повторение", callback_data="edit_recurrence"),
        )
        markup.add(
            types.InlineKeyboardButton("📎 Файл", callback_data="edit_file"),
        )
        markup.add(
            types.InlineKeyboardButton("✅ Подтвердить изменения", callback_data="confirm_edit"),
            types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_edit")
        )

        bot.send_message(telegram_id, "Выберите, что хотите изменить:", reply_markup=markup)
    except:
        bot.send_message(telegram_id, "Ошибка при загрузке события.")

@bot.callback_query_handler(func=lambda call: call.data == "edit_title")
def edit_title(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Введите новое название:")
    bot.register_next_step_handler(call.message, save_edited_title)

def save_edited_title(message):
    event_data[message.chat.id]['title'] = message.text
    bot.send_message(message.chat.id, "Название обновлено. Вы можете изменить другие параметры или нажать ✅ Подтвердить.")

@bot.callback_query_handler(func=lambda call: call.data == "edit_description")
def edit_description(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Введите новое описание:")
    bot.register_next_step_handler(call.message, save_edited_description)

def save_edited_description(message):
    event_data[message.chat.id]['description'] = message.text
    bot.send_message(message.chat.id, "Описание обновлено. Вы можете изменить другие параметры или нажать ✅ Подтвердить.")

@bot.callback_query_handler(func=lambda call: call.data == "edit_date")
def edit_date(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Введите новую дату в формате ГГГГ-ММ-ДД ЧЧ:ММ:")
    bot.register_next_step_handler(call.message, save_edited_date)

def save_edited_date(message):
    try:
        naive_dt = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        moscow = timezone("Europe/Moscow")
        aware_dt = moscow.localize(naive_dt)
        event_data[message.chat.id]['date'] = aware_dt
        bot.send_message(message.chat.id, "Дата обновлена. Вы можете изменить другие параметры или нажать ✅ Подтвердить.")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат. Попробуйте ещё раз (ГГГГ-ММ-ДД ЧЧ:ММ):")
        bot.register_next_step_handler(message, save_edited_date)

@bot.callback_query_handler(func=lambda call: call.data == "edit_recurrence")
def edit_recurrence(call):
    bot.answer_callback_query(call.id)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('Без повторения', 'Ежедневно')
    markup.add('Еженедельно', 'Раз в 2 недели', 'Ежемесячно')
    bot.send_message(call.message.chat.id, "Выберите тип повторения:", reply_markup=markup)
    bot.register_next_step_handler(call.message, save_edited_recurrence)

def save_edited_recurrence(message):
    recurrence_mapping = {
        'Без повторения': 'none',
        'Ежедневно': 'daily',
        'Еженедельно': 'weekly',
        'Раз в 2 недели': 'biweekly',
        'Ежемесячно': 'monthly',
    }

    value = recurrence_mapping.get(message.text)
    if not value:
        bot.send_message(message.chat.id, "Неверный выбор. Попробуйте снова.")
        bot.register_next_step_handler(message, save_edited_recurrence)
        return

    event_data[message.chat.id]['recurrence'] = value
    bot.send_message(message.chat.id, "Тип повторения обновлён. Вы можете изменить другие параметры или нажать ✅ Подтвердить.")

@bot.callback_query_handler(func=lambda call: call.data == "edit_file")
def edit_file(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Отправьте новый файл или введите 'Пропустить':")
    bot.register_next_step_handler(call.message, save_edited_file)

def save_edited_file(message):
    telegram_id = message.chat.id

    if message.text and message.text.lower() == 'пропустить':
        event_data[telegram_id]['file'] = None
        bot.send_message(telegram_id, "Файл удалён. Можете изменить другие поля или нажать ✅ Подтвердить.")
        return

    if message.document:
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = message.document.file_name

        os.makedirs(os.path.join(settings.MEDIA_ROOT, 'event_files'), exist_ok=True)
        file_path = os.path.join(settings.MEDIA_ROOT, 'event_files', file_name)

        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        event_data[telegram_id]['file'] = file_path
        bot.send_message(telegram_id, "Файл обновлён. Можете изменить другие поля или нажать ✅ Подтвердить.")
    else:
        bot.send_message(telegram_id, "Пожалуйста, отправьте документ или введите 'Пропустить'.")
        bot.register_next_step_handler(message, save_edited_file)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_edit")
def cancel_editing(call):
    bot.answer_callback_query(call.id)
    telegram_id = call.message.chat.id
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=None
    )
    event_data.pop(telegram_id, None)
    bot.send_message(telegram_id, "Редактирование отменено.")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_edit")
def confirm_event_edit(call):
    bot.answer_callback_query(call.id)
    telegram_id = call.message.chat.id
    data = event_data.get(telegram_id)
    if not data:
        bot.send_message(telegram_id, "Ошибка: данные не найдены.")
        return

    try:
        event = Event.objects.get(id=data['event_id'])
        event.title = data['title']
        event.description = data['description']
        event.date = data['date']
        event.recurrence = data.get('recurrence', 'none')
        if data.get('file'):
            event.file.name = f"event_files/{os.path.basename(data['file'])}"
        event.save()
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )
        # Уведомление участникам
        from .models import EventResponse
        responses = EventResponse.objects.filter(event=event, response='yes').select_related('student__user')
        for r in responses:
            try:
                bot.send_message(
                    r.student.user.telegram_id,
                    f"🔔 Обновление события, на которое вы записались:\n"
                    f"Название: {event.title}\n"
                    f"Описание: {event.description}\n"
                    f"Дата: {event.date.strftime('%d.%m.%Y %H:%M')}"
                )
                if event.file and os.path.exists(event.file.path):
                    with open(event.file.path, 'rb') as f:
                        bot.send_document(r.student.user.telegram_id, f)
            except Exception as e:
                logging.error(f"Не удалось уведомить {r.student.user.telegram_id}: {e}")

        bot.send_message(telegram_id, "✅ Событие обновлено и участники уведомлены.")
        event_data.pop(telegram_id, None)

    except Exception as e:
        bot.send_message(telegram_id, f"Ошибка при сохранении: {str(e)}")

# Запуск бота
def start_bot():
    set_bot_commands()
    
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or os.environ.get('RUN_MAIN') == 'true':
        print("Бот запущен!")
        try:
            bot.polling(none_stop=True, skip_pending=True)
        except Exception as e:
            print(f"Ошибка в работе бота: {e}")

import atexit

def stop_bot():
    try:
        bot.stop_polling()
    except Exception as e:
        print(f"Ошибка при остановке бота: {e}")

atexit.register(stop_bot)