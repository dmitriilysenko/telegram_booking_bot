from datetime import datetime, timedelta
from django.utils import timezone
from telebot.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from bot_app.models import User, Booking, Review
from bot_app.core import bot, logger, is_admin
from bot_app.config import WEEKDAY_NAMES, BOOKING_OPEN_HOUR
from bot_app.services.schedule import (
get_week_range, get_slots_for_week, get_current_week_start, format_slot
)
from bot_app.keyboards import (
    get_navigation_keyboard, get_registration_keyboard, get_registration_text,
)


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

@bot.message_handler(commands=['start'])
def start_command(message: Message):
    user, created = User.objects.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'display_name': message.from_user.first_name,
        }
    )
    if created:
        logger.info(f'Новый пользователь: {user}')
        for staff in User.objects.filter(is_staff=True):
            try:
                bot.send_message(
                    staff.telegram_id,
                    get_registration_text(user),
                    reply_markup=get_registration_keyboard(user),
                )
            except Exception as e:
                logger.error(f'Уведомление админу: {e}')
        text = (
            f'👋 Привет, {user.first_name}!\n'
            'Ты зарегистрирован. Используй кнопки ниже:'
        )
    else:
        text = f'👋 С возвращением, {user.first_name}!'
    bot.send_message(message.chat.id, text, reply_markup=get_navigation_keyboard())

@bot.message_handler(commands=['profile'])
def profile_command(message: Message):
    user = get_user_from_message(message)
    if not user:
        return
    text = (
        f'👤 *Личный кабинет*\n\n'
        f'Имя: {user.display_name}\n'
        f'Username: @{user.username or "—"}\n'
        f'Airsoft: {"✅" if user.is_airsoft_member else "❌"}\n'
        f'Пол: {"👦" if user.gender == "M" else "👧" if user.gender == "F" else "—"}\n'
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton('✏️ Изменить имя', callback_data='profile_edit_name'),
        InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'),
    ).add(
        InlineKeyboardButton('✍️ Оставить отзыв', callback_data='review'),
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=kb)

@bot.message_handler(commands=['reviews'])
def reviews_command(message: Message):
    user = get_user_from_message(message)
    if not user or not is_admin(user):
        bot.send_message(message.chat.id, '❌ Нет доступа')
        return
    reviews = Review.objects.select_related('user')[:20]
    if not reviews:
        bot.send_message(message.chat.id, 'Отзывов нет')
        return
    text = '\n\n'.join(
        f'👤 {r.user.display_name} ({r.created_at:%d.%m %H:%M}):\n{r.text}'
        for r in reviews
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['main'])
def main_command(message: Message):
    """Показывает список доступных команд"""
    text = f"""
🤖 Доступные команды:

/start — регистрация в системе
/schedule — посмотреть расписание
/book — записаться на занятие
/my_bookings — мои записи
/cancel — отменить последнюю запись
/main — эта справка

📌 Количество мест: 2 человека на слот
📌 Ограничения:
  • Запись открывается в понедельник в {BOOKING_OPEN_HOUR}:00
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
        text = f"📅 На неделе {week_range} больше нет доступных слотов.\n\nСледующая неделя откроется в понедельник в {BOOKING_OPEN_HOUR}:00."
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
        text += f'📍 {day_name}\n'
        for slot in day_slots:
            line = f'  {format_slot(slot)}'
            if slot['names']:
                line += f' — {", ".join(slot["names"])}'
            text += line + '\n'
        text += '\n'

    # Информация о времени открытия записи
    monday_open = timezone.make_aware(
        datetime.combine(week_start, datetime.min.time()).replace(
            hour=BOOKING_OPEN_HOUR, minute=0
        )
    )
    now = timezone.localtime(timezone.now())

    if now < monday_open:
        text += f"\n⏳ Запись откроется в *понедельник в {BOOKING_OPEN_HOUR}:00*"
    else:
        text += f"\n✅ Запись открыта! Используй кнопку ниже."

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Записаться", callback_data="book"),
        InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings")
    )
    keyboard.add(
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
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

    # Проверка: можно ли записываться (после BOOKING_OPEN_HOUR понедельника)
    monday_open = timezone.make_aware(
        datetime.combine(week_start, datetime.min.time()).replace(
            hour=BOOKING_OPEN_HOUR, minute=0
        )
    )
    now = timezone.localtime(timezone.now())

    if now < monday_open:
        time_left = monday_open - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60

        text = (
            f"⏳ Запись на неделю {week_range} откроется в *понедельник в {BOOKING_OPEN_HOUR}:00*!\n\n"
            f"Осталось: {hours} ч {minutes} мин\n\n"
            f"📅 Следующая неделя откроется: {week_start.strftime('%d.%m')} в {BOOKING_OPEN_HOUR}:00"
        )
        keyboard = get_navigation_keyboard()
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    available = [s for s in slots if s['is_available']]

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

@bot.message_handler(commands=['my_bookings'])
def my_bookings_command(message: Message):
    """Показывает активные записи пользователя на текущую неделю"""
    user = get_user_from_message(message)
    if not user:
        return

    # Получаем начало и конец текущей недели
    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)

    # Фильтруем: только активные и только на текущей неделе
    bookings = Booking.objects.filter(
        user=user,
        is_active=True,
        date__gte=week_start,
        date__lte=week_end
    ).order_by('date', 'time')

    if not bookings:
        text = '📭 У тебя нет активных записей на текущую неделю.'
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton('📝 Записаться', callback_data='book'),
            InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'),
        )
        keyboard.add(
            InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main"))
        bot.send_message(message.chat.id, text, reply_markup=keyboard)
        return

    text = f"📋 Твои записи на неделю {get_week_range(week_start)}:\n\n"
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
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['cancel'])
def cancel_command(message: Message):
    """Быстрая отмена последней записи на текущей неделе"""
    user = get_user_from_message(message)
    if not user:
        return

    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)

    booking = Booking.objects.filter(
        user=user,
        is_active=True,
        date__gte=week_start,
        date__lte=week_end
    ).order_by('-created_at').first()

    if not booking:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton('📝 Записаться', callback_data='book'),
            InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'),
        )
        bot.send_message(
            message.chat.id,
            '📭 У тебя нет активных записей на текущую неделю.',
            reply_markup=kb,
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
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
    )

    bot.send_message(
        message.chat.id,
        f"❌ Запись на {booking.date.strftime('%d.%m')} "
        f"{booking.time.strftime('%H:%M')} отменена.",
        reply_markup=keyboard
    )