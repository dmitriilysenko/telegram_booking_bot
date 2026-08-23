"""
Основная логика Telegram-бота для записи на занятия
Только кнопки (без текстового ввода)
"""

import logging
from datetime import date, datetime, timedelta
from django.conf import settings
from django.db import IntegrityError
from telebot import TeleBot
from telebot.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

from .models import User, Booking
from .config import (
    MAX_PEOPLE_PER_SLOT,
    VALID_SLOTS,
    WEEKDAY_NAMES,
    WEEKDAY_NAMES_SHORT,
    is_valid_slot,
)

# ============================================
# НАСТРОЙКА
# ============================================

logger = logging.getLogger(__name__)
bot = TeleBot(settings.BOT_TOKEN)

# Берём из настроек (которые из .env)
GROUP_CHAT_ID = getattr(settings, 'GROUP_CHAT_ID', None)
BOT_LINK = getattr(settings, 'BOT_LINK', 'https://t.me/your_bot')


# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def get_current_week_start() -> date:
    """Возвращает дату понедельника текущей недели"""
    today = date.today()
    return today - timedelta(days=today.weekday())


def get_week_range(week_start: date) -> str:
    """Возвращает строку с диапазоном дат недели"""
    week_end = week_start + timedelta(days=6)
    return f"{week_start.strftime('%d.%m')} – {week_end.strftime('%d.%m')}"


def get_user_by_telegram_id(telegram_id: int):
    """Получает пользователя из БД по telegram_id"""
    return User.objects.filter(telegram_id=telegram_id).first()


def get_user_from_message(message: Message):
    """Получает пользователя из сообщения, если он зарегистрирован"""
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        bot.send_message(
            message.chat.id,
            "❌ Ты не зарегистрирован! Напиши /start"
        )
        return None
    return user


def get_user_from_callback(call: CallbackQuery):
    """Получает пользователя из callback'а"""
    telegram_id = call.from_user.id
    logger.info(f"🔍 Ищу пользователя с ID: {telegram_id}")

    user = User.objects.filter(telegram_id=telegram_id).first()

    if user:
        logger.info(f"✅ Пользователь найден: {user}")
        bot.answer_callback_query(call.id, f"👋 Привет, {user.first_name}!")
    else:
        logger.warning(f"❌ Пользователь НЕ найден!")
        bot.answer_callback_query(call.id, "❌ Сначала напиши /start")
        bot.send_message(
            call.message.chat.id,
            "❌ Ты не зарегистрирован! Напиши /start"
        )
        return None

    return user


def get_slots_for_week(week_start: date = None, show_past: bool = False) -> list:
    """
    Возвращает все слоты на неделю с информацией о заполненности

    Args:
        week_start: дата понедельника
        show_past: показывать ли прошедшие даты (по умолчанию False)
    """
    if week_start is None:
        week_start = get_current_week_start()

    result = []
    today = date.today()

    for day, time_obj in VALID_SLOTS:
        days_ahead = day - week_start.weekday()
        if days_ahead < 0:
            days_ahead += 7
        dt = week_start + timedelta(days=days_ahead)

        # Пропускаем прошедшие даты, если show_past=False
        if not show_past and dt < today:
            continue

        booked_count = Booking.objects.filter(
            date=dt,
            time=time_obj,
            is_active=True
        ).count()

        is_full = booked_count >= MAX_PEOPLE_PER_SLOT

        result.append({
            'date': dt,
            'time': time_obj,
            'day': day,
            'day_name': WEEKDAY_NAMES[day],
            'day_name_short': WEEKDAY_NAMES_SHORT[day],
            'booked_count': booked_count,
            'max_people': MAX_PEOPLE_PER_SLOT,
            'free_slots': MAX_PEOPLE_PER_SLOT - booked_count,
            'is_full': is_full,
            'is_available': not is_full,
        })

    return result


def format_slot(slot: dict) -> str:
    """
    Форматирует слот для отображения в тексте

    Примеры:
    - 🟢 11:00 — доступно 2 места
    - 🟡 11:30 — доступно 1 место
    - 🔴 12:00 — мест нет
    """
    time_str = slot['time'].strftime('%H:%M')

    if slot['is_full']:
        return f"🔴 {time_str} — мест нет"
    elif slot['free_slots'] == 1:
        return f"🟡 {time_str} — доступно 1 место"
    else:
        return f"🟢 {time_str} — доступно {slot['free_slots']} места"


def format_schedule_text(week_start: date = None) -> str:
    """Форматирует полное расписание для отправки в группу"""
    if week_start is None:
        week_start = get_current_week_start()

    week_range = get_week_range(week_start)

    # Для уведомлений показываем ВСЕ слоты (включая прошедшие)
    # чтобы было понятно, что неделя закрывается
    slots = get_slots_for_week(week_start, show_past=True)

    grouped = {}
    for slot in slots:
        day_name = slot['day_name']
        if day_name not in grouped:
            grouped[day_name] = []
        grouped[day_name].append(slot)

    text = f"📅 *Расписание на неделю {week_range}*\n\n"

    for day_name, day_slots in grouped.items():
        text += f"📍 *{day_name}*\n"
        for slot in day_slots:
            text += f"  {format_slot(slot)}\n"
        text += "\n"

    text += f"\n✏️ Записаться: {BOT_LINK}"

    return text


def parse_booking_callback_data(data: str):
    """Парсит callback_data кнопки записи"""
    try:
        _, date_str, time_str = data.split('_')
        dt = datetime.strptime(date_str, '%Y%m%d').date()
        time_obj = datetime.strptime(time_str, '%H%M').time()
        return dt, time_obj
    except (ValueError, IndexError):
        return None


def check_booking_limits(user, dt: date) -> tuple:
    """
    Проверяет ограничения для пользователя:
    - Нельзя записаться на прошлое
    - Нельзя записаться ранее 9:00 понедельника
    - Не более 1 записи в день
    - Не более 3 записей в неделю

    Возвращает (is_allowed, message)
    """
    # Проверка: нельзя записаться на прошлое
    today = date.today()
    if dt < today:
        return False, "❌ Нельзя записаться на прошедшую дату! Выбери будущую дату."

    # Проверка: нельзя записаться ранее 9:00 понедельника
    week_start = get_current_week_start()
    monday_9am = datetime.combine(week_start, datetime.min.time()).replace(hour=9, minute=0)
    now = datetime.now()

    if now < monday_9am:
        time_left = monday_9am - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        return False, (
            f"❌ Запись на неделю открывается в *понедельник в 9:00*!\n"
            f"⏳ Осталось: {hours} ч {minutes} мин\n\n"
            f"📅 Следующая неделя откроется: {week_start.strftime('%d.%m')} в 9:00"
        )

    # Проверка: не более 1 записи в день
    today_bookings = Booking.objects.filter(
        user=user,
        date=dt,
        is_active=True
    ).count()

    if today_bookings >= 1:
        return False, "❌ У тебя уже есть запись на этот день! Максимум 1 запись в день."

    # Проверка: не более 3 записей в неделю
    week_end = week_start + timedelta(days=6)

    week_bookings = Booking.objects.filter(
        user=user,
        date__gte=week_start,
        date__lte=week_end,
        is_active=True
    ).count()

    if week_bookings >= 3:
        return False, f"❌ У тебя уже есть {week_bookings} записей на этой неделе! Максимум 3 записи в неделю."

    return True, "✅ Ограничения пройдены"


def send_group_notification(user, dt: date, time_obj):
    """
    Отправляет уведомление в группу о новой записи:
    1) Сообщение: участник записался
    2) Актуальное расписание
    """
    if not GROUP_CHAT_ID:
        logger.warning("⚠️ GROUP_CHAT_ID не задан! Уведомления не отправляются.")
        return

    day_name = WEEKDAY_NAMES[dt.weekday()]
    username = f"@{user.username}" if user.username else user.first_name

    # Сообщение 1: участник записался
    msg1 = (
        f"📝 *Новая запись!*\n\n"
        f"👤 {username} записался на занятие:\n"
        f"📅 {day_name} {dt.strftime('%d.%m')}\n"
        f"⏰ {time_obj.strftime('%H:%M')}"
    )

    try:
        bot.send_message(GROUP_CHAT_ID, msg1, parse_mode="Markdown")
        logger.info(f"✅ Уведомление в группу отправлено: {user} -> {dt} {time_obj}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

    # Сообщение 2: актуальное расписание
    schedule_text = format_schedule_text()
    try:
        bot.send_message(GROUP_CHAT_ID, schedule_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки расписания: {e}")


def get_navigation_keyboard(show_my_bookings: bool = True, show_schedule: bool = True, show_help: bool = True):
    """
    Создаёт навигационную клавиатуру с кнопками
    """
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []

    if show_my_bookings:
        buttons.append(InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings"))
    if show_schedule:
        buttons.append(InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule"))
    if show_help:
        buttons.append(InlineKeyboardButton("❓ Помощь", callback_data="nav_help"))

    keyboard.add(*buttons)
    return keyboard


# ============================================
# КОМАНДЫ БОТА
# ============================================

@bot.message_handler(commands=['start'])
def start_command(message: Message):
    """Регистрирует пользователя в системе"""
    user, created = User.objects.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
        }
    )

    if created:
        logger.info(f"Новый пользователь: {user}")
        text = (
            f"👋 Привет, {user.first_name}!\n"
            "Ты успешно зарегистрирован в системе записи.\n\n"
            "📌 Используй кнопки ниже для навигации:"
        )
    else:
        text = (
            f"👋 С возвращением, {user.first_name}!\n\n"
            "📌 Используй кнопки ниже для навигации:"
        )

    keyboard = get_navigation_keyboard()
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['help'])
def help_command(message: Message):
    """Показывает список доступных команд"""
    text = """
🤖 Доступные команды:

/start — регистрация в системе
/schedule — посмотреть расписание
/book — записаться на занятие
/my_bookings — мои записи
/cancel — отменить последнюю запись
/help — эта справка

📌 Количество мест: 2 человека на слот
📌 Ограничения:
  • Запись открывается в понедельник в 9:00
  • Нельзя записаться на прошлое
  • 1 запись в день
  • 3 записи в неделю
"""
    keyboard = get_navigation_keyboard()
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['schedule'])
def schedule_command(message: Message):
    """Показывает расписание на текущую неделю с кнопкой записи"""
    week_start = get_current_week_start()
    week_range = get_week_range(week_start)

    # Показываем только будущие и сегодняшние слоты
    slots = get_slots_for_week(week_start, show_past=False)

    if not slots:
        text = f"📅 На неделе {week_range} больше нет доступных слотов.\n\nСледующая неделя откроется в понедельник в 9:00."
        keyboard = get_navigation_keyboard()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=keyboard
        )
        return

    grouped = {}
    for slot in slots:
        day_name = slot['day_name']
        if day_name not in grouped:
            grouped[day_name] = []
        grouped[day_name].append(slot)

    text = f"📅 Расписание на неделю {week_range}\n\n"

    for day_name, day_slots in grouped.items():
        text += f"📍 {day_name}\n"
        for slot in day_slots:
            text += f"  {format_slot(slot)}\n"
        text += "\n"

    # Информация о времени открытия записи
    monday_9am = datetime.combine(week_start, datetime.min.time()).replace(hour=9, minute=0)
    now = datetime.now()

    if now < monday_9am:
        text += f"\n⏳ Запись откроется в *понедельник в 9:00*"
    else:
        text += f"\n✅ Запись открыта! Используй кнопку ниже."

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Записаться", callback_data="book"),
        InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings")
    )
    keyboard.add(
        InlineKeyboardButton("❓ Помощь", callback_data="nav_help")
    )

    bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@bot.message_handler(commands=['book'])
def book_command(message: Message):
    """Начинает процесс записи — показывает доступные слоты"""
    user = get_user_from_message(message)
    if not user:
        return

    week_start = get_current_week_start()
    week_range = get_week_range(week_start)
    slots = get_slots_for_week(week_start, show_past=False)

    # Проверка: можно ли записываться (после 9:00 понедельника)
    monday_9am = datetime.combine(week_start, datetime.min.time()).replace(hour=9, minute=0)
    now = datetime.now()

    if now < monday_9am:
        time_left = monday_9am - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60

        text = (
            f"⏳ Запись на неделю {week_range} откроется в *понедельник в 9:00*!\n\n"
            f"Осталось: {hours} ч {minutes} мин\n\n"
            f"📅 Следующая неделя откроется: {week_start.strftime('%d.%m')} в 9:00"
        )
        keyboard = get_navigation_keyboard()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # Исключаем прошедшие даты
    today = date.today()
    available = [s for s in slots if s['is_available'] and s['date'] >= today]

    if not available:
        text = f"😞 На неделе {week_range} нет свободных мест."
        keyboard = get_navigation_keyboard()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardMarkup(row_width=2)

    for slot in available:
        date_str = slot['date'].strftime('%Y%m%d')
        time_str = slot['time'].strftime('%H%M')
        callback_data = f"book_{date_str}_{time_str}"

        button_text = (
            f"{slot['day_name_short']} {slot['time'].strftime('%H:%M')} "
            f"({slot['free_slots']} мест)"
        )
        keyboard.add(InlineKeyboardButton(button_text, callback_data=callback_data))

    keyboard.add(
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_book"),
        InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings")
    )

    bot.send_message(
        message.chat.id,
        f"📝 Выбери слот для записи на неделю {week_range}:",
        reply_markup=keyboard
    )


# ============================================
# CALLBACK-ОБРАБОТЧИКИ
# ============================================

@bot.callback_query_handler(func=lambda call: call.data == "book")
def book_from_schedule_callback(call: CallbackQuery):
    """Обработчик кнопки 'Записаться' из расписания"""
    bot.answer_callback_query(call.id)

    user = get_user_from_callback(call)
    if not user:
        return

    # Создаём фейковое сообщение для вызова book_command
    class FakeMessage:
        def __init__(self, chat_id, from_user):
            self.chat = type('obj', (object,), {'id': chat_id})
            self.from_user = from_user

    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    book_command(fake_message)


@bot.callback_query_handler(func=lambda call: call.data == "cancel_book")
def cancel_book_callback(call: CallbackQuery):
    """Отменяет процесс записи"""
    bot.answer_callback_query(call.id)
    keyboard = get_navigation_keyboard()
    bot.edit_message_text(
        "❌ Запись отменена.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("book_"))
def confirm_booking_callback(call: CallbackQuery):
    """Обработчик выбора слота — создаёт запись"""
    bot.answer_callback_query(call.id, "⏳ Обрабатываю запрос...")

    user = get_user_from_callback(call)
    if not user:
        return

    parsed = parse_booking_callback_data(call.data)
    if not parsed:
        bot.answer_callback_query(call.id, "❌ Ошибка! Попробуй снова.")
        return

    dt, time_obj = parsed
    day = dt.weekday()

    # Проверка: существует ли слот?
    if not is_valid_slot(day, time_obj):
        bot.answer_callback_query(call.id, "❌ Такого слота не существует!")
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            f"❌ Слот {WEEKDAY_NAMES[day]} {time_obj.strftime('%H:%M')} не существует!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
        return

    # Проверка: не записан ли уже?
    if Booking.objects.filter(user=user, date=dt, time=time_obj, is_active=True).exists():
        bot.answer_callback_query(call.id, "❌ Ты уже записан!")
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            f"❌ Ты уже записан на {WEEKDAY_NAMES[day]} {time_obj.strftime('%H:%M')}!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
        return

    # Проверка: есть ли места?
    booked_count = Booking.objects.filter(date=dt, time=time_obj, is_active=True).count()
    if booked_count >= MAX_PEOPLE_PER_SLOT:
        bot.answer_callback_query(call.id, "😞 Мест больше нет!")
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            f"😞 На {WEEKDAY_NAMES[day]} {time_obj.strftime('%H:%M')} мест больше нет.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
        return

    # Проверка ограничений: 1 запись в день, 3 в неделю, нельзя на прошлое
    is_allowed, limit_message = check_booking_limits(user, dt)
    if not is_allowed:
        bot.answer_callback_query(call.id, "❌ Превышен лимит записей!")
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            f"{limit_message}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # Создаём запись
    try:
        Booking.objects.create(user=user, date=dt, time=time_obj, is_active=True)
        logger.info(f"Создана запись: {user} -> {dt} {time_obj}")

        bot.answer_callback_query(call.id, f"✅ Запись на {time_obj.strftime('%H:%M')} создана!")

        # Отправляем уведомление в группу
        send_group_notification(user, dt, time_obj)

        # Клавиатура с навигацией
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings"),
            InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule")
        )
        keyboard.add(
            InlineKeyboardButton("❓ Помощь", callback_data="nav_help")
        )

        bot.edit_message_text(
            f"✅ Ты записался!\n\n"
            f"📅 {WEEKDAY_NAMES[day]} {dt.strftime('%d.%m')}\n"
            f"⏰ {time_obj.strftime('%H:%M')}\n\n"
            f"Мест осталось: {MAX_PEOPLE_PER_SLOT - booked_count - 1}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )

    except IntegrityError:
        bot.answer_callback_query(call.id, "❌ Ты уже записан!")
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            "❌ Произошла ошибка. Возможно, ты уже записан.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )


@bot.message_handler(commands=['my_bookings'])
def my_bookings_command(message: Message):
    """Показывает все активные записи пользователя"""
    user = get_user_from_message(message)
    if not user:
        return

    bookings = Booking.objects.filter(user=user, is_active=True).order_by('date', 'time')

    if not bookings:
        text = "📭 У тебя нет активных записей."
        keyboard = get_navigation_keyboard()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=keyboard
        )
        return

    text = "📋 Твои записи:\n\n"
    for booking in bookings:
        day_name = WEEKDAY_NAMES[booking.date.weekday()]
        text += (
            f"• {day_name} {booking.date.strftime('%d.%m')} — "
            f"{booking.time.strftime('%H:%M')}\n"
        )

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("❌ Отменить запись", callback_data="cancel_booking"),
        InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule")
    )
    keyboard.add(
        InlineKeyboardButton("❓ Помощь", callback_data="nav_help")
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['cancel'])
def cancel_command(message: Message):
    """Быстрая отмена последней записи"""
    user = get_user_from_message(message)
    if not user:
        return

    booking = Booking.objects.filter(user=user, is_active=True).order_by('-created_at').first()
    if not booking:
        text = "📭 У тебя нет активных записей."
        keyboard = get_navigation_keyboard()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=keyboard
        )
        return

    booking.is_active = False
    booking.save()
    logger.info(f"Отменена запись: {booking}")

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings"),
        InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule")
    )
    keyboard.add(
        InlineKeyboardButton("❓ Помощь", callback_data="nav_help")
    )

    bot.send_message(
        message.chat.id,
        f"❌ Запись на {booking.date.strftime('%d.%m')} "
        f"{booking.time.strftime('%H:%M')} отменена.",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_booking")
def cancel_booking_callback(call: CallbackQuery):
    """Начинает процесс отмены записи"""
    bot.answer_callback_query(call.id)

    user = get_user_from_callback(call)
    if not user:
        return

    bookings = Booking.objects.filter(user=user, is_active=True).order_by('date', 'time')

    if not bookings:
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            "📭 У тебя нет активных записей для отмены.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
        return

    # Если одна запись — отменяем сразу
    if len(bookings) == 1:
        booking = bookings.first()
        booking.is_active = False
        booking.save()
        logger.info(f"Отменена запись: {booking}")

        bot.answer_callback_query(call.id, "✅ Запись отменена!")

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings"),
            InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule")
        )
        keyboard.add(
            InlineKeyboardButton("❓ Помощь", callback_data="nav_help")
        )

        bot.edit_message_text(
            f"❌ Запись на {booking.date.strftime('%d.%m')} "
            f"{booking.time.strftime('%H:%M')} отменена.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
        return

    # Если несколько — показываем выбор
    keyboard = InlineKeyboardMarkup(row_width=2)

    for booking in bookings:
        date_str = booking.date.strftime('%Y%m%d')
        time_str = booking.time.strftime('%H%M')
        callback_data = f"cancel_{date_str}_{time_str}"

        day_name = WEEKDAY_NAMES_SHORT[booking.date.weekday()]
        button_text = (
            f"{day_name} {booking.date.strftime('%d.%m')} "
            f"{booking.time.strftime('%H:%M')}"
        )
        keyboard.add(InlineKeyboardButton(button_text, callback_data=callback_data))

    keyboard.add(
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_cancel"),
        InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings")
    )

    bot.edit_message_text(
        "Выбери запись для отмены:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_cancel")
def cancel_cancel_callback(call: CallbackQuery):
    """Отмена отмены"""
    bot.answer_callback_query(call.id)
    bot.delete_message(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    keyboard = get_navigation_keyboard()
    bot.send_message(
        call.message.chat.id,
        "❌ Отмена отменена. Твои записи сохранены.",
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def confirm_cancel_callback(call: CallbackQuery):
    """Подтверждает отмену конкретной записи"""
    bot.answer_callback_query(call.id)

    user = get_user_from_callback(call)
    if not user:
        return

    try:
        _, date_str, time_str = call.data.split('_')
        dt = datetime.strptime(date_str, '%Y%m%d').date()
        time_obj = datetime.strptime(time_str, '%H%M').time()
    except (ValueError, IndexError):
        bot.send_message(call.message.chat.id, "❌ Ошибка! Попробуй снова.")
        return

    booking = Booking.objects.filter(
        user=user,
        date=dt,
        time=time_obj,
        is_active=True
    ).first()

    if not booking:
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            "❌ Запись не найдена или уже отменена.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
        return

    booking.is_active = False
    booking.save()
    logger.info(f"Отменена запись: {booking}")

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings"),
        InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule")
    )
    keyboard.add(
        InlineKeyboardButton("❓ Помощь", callback_data="nav_help")
    )

    bot.edit_message_text(
        f"❌ Запись на {dt.strftime('%d.%m')} {time_obj.strftime('%H:%M')} отменена.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )


# ============================================
# НАВИГАЦИОННЫЕ CALLBACK-ОБРАБОТЧИКИ
# ============================================

@bot.callback_query_handler(func=lambda call: call.data == "nav_my_bookings")
def nav_my_bookings_callback(call: CallbackQuery):
    """Навигация в /my_bookings"""
    bot.answer_callback_query(call.id)

    class FakeMessage:
        def __init__(self, chat_id, from_user):
            self.chat = type('obj', (object,), {'id': chat_id})
            self.from_user = from_user

    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    my_bookings_command(fake_message)


@bot.callback_query_handler(func=lambda call: call.data == "nav_schedule")
def nav_schedule_callback(call: CallbackQuery):
    """Навигация в /schedule"""
    bot.answer_callback_query(call.id)

    class FakeMessage:
        def __init__(self, chat_id, from_user):
            self.chat = type('obj', (object,), {'id': chat_id})
            self.from_user = from_user

    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    schedule_command(fake_message)


@bot.callback_query_handler(func=lambda call: call.data == "nav_help")
def nav_help_callback(call: CallbackQuery):
    """Навигация в /help"""
    bot.answer_callback_query(call.id)

    class FakeMessage:
        def __init__(self, chat_id, from_user):
            self.chat = type('obj', (object,), {'id': chat_id})
            self.from_user = from_user

    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    help_command(fake_message)


@bot.message_handler(func=lambda message: True)
def echo_all(message: Message):
    """Ответ на любое сообщение, не являющееся командой"""
    keyboard = get_navigation_keyboard()
    bot.send_message(
        message.chat.id,
        "😅 Я не понимаю это сообщение\n"
        "Используй кнопки ниже для навигации:",
        reply_markup=keyboard
    )


def run_bot():
    """Запускает бота"""
    logger.info("🚀 Бот запущен!")
    logger.info(f"📊 Загружено {len(VALID_SLOTS)} слотов")
    logger.info(f"👥 Максимум человек на слот: {MAX_PEOPLE_PER_SLOT}")

    if GROUP_CHAT_ID:
        logger.info(f"📢 Уведомления в группу: включены (ID: {GROUP_CHAT_ID})")
    else:
        logger.warning("⚠️ Уведомления в группу: ОТКЛЮЧЕНЫ (GROUP_CHAT_ID не задан)")

    logger.info(f"🔗 Ссылка на бота: {BOT_LINK}")

    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"❌ Ошибка при работе бота: {e}")
        raise