from datetime import datetime, timedelta
from django.db import IntegrityError
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

from bot_app.models import Booking, User
from bot_app.core import bot, logger, FakeMessage
from bot_app.config import (
    MAX_PEOPLE_PER_SLOT,
    WEEKDAY_NAMES,
    WEEKDAY_NAMES_SHORT,
    is_valid_slot,
)
from .commands import book_command
from bot_app.keyboards import get_navigation_keyboard
from bot_app.services.schedule import get_current_week_start
from bot_app.services.booking import send_group_notification, check_booking_limits


def parse_booking_callback_data(data: str):
    """Парсит callback_data кнопки записи"""
    try:
        _, date_str, time_str = data.split('_')
        dt = datetime.strptime(date_str, '%Y%m%d').date()
        time_obj = datetime.strptime(time_str, '%H%M').time()
        return dt, time_obj
    except (ValueError, IndexError):
        return None

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

@bot.callback_query_handler(func=lambda call: call.data == "book")
def book_from_schedule_callback(call: CallbackQuery):
    """Обработчик кнопки 'Записаться' из расписания"""
    bot.answer_callback_query(call.id)

    user = get_user_from_callback(call)
    if not user:
        return

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

@bot.callback_query_handler(func=lambda call: call.data == "cancel_booking")
def cancel_booking_callback(call: CallbackQuery):
    """Начинает процесс отмены записи на текущей неделе"""
    bot.answer_callback_query(call.id)

    user = get_user_from_callback(call)
    if not user:
        return

    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)

    bookings = Booking.objects.filter(
        user=user,
        is_active=True,
        date__gte=week_start,
        date__lte=week_end
    ).order_by('date', 'time')

    if not bookings:
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            "📭 У тебя нет активных записей на текущую неделю.",
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
    """Подтверждает отмену конкретной записи на текущей неделе"""
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

    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)

    # Проверяем, что запись на текущей неделе
    if dt < week_start or dt > week_end:
        keyboard = get_navigation_keyboard()
        bot.edit_message_text(
            "❌ Эта запись не на текущей неделе.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
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