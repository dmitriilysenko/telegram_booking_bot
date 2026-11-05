from datetime import datetime, timedelta

from django.db import IntegrityError
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from bot_app.models import (
    Booking, User, Review, AirsoftConfirmation,
)
from bot_app.core import (
    bot, logger, FakeMessage, get_trainers,
)
from bot_app.config import (
    MAX_PEOPLE_PER_SLOT,
    WEEKDAY_NAMES,
    WEEKDAY_NAMES_SHORT,
    is_valid_slot,
)
from bot_app.keyboards import get_navigation_keyboard
from bot_app.services.schedule import get_current_week_start
from bot_app.services.booking import check_booking_limits
from .commands import book_command, get_user_from_message


def parse_booking_callback_data(data: str):
    """Парсит callback_data кнопки записи: 'book_YYYYMMDD_HHMM' -> (date, time)"""
    try:
        _, date_str, time_str = data.split('_')
        dt = datetime.strptime(date_str, '%Y%m%d').date()
        time_obj = datetime.strptime(time_str, '%H%M').time()
        return dt, time_obj
    except (ValueError, IndexError):
        return None

def get_user_from_callback(call: CallbackQuery):
    """Достаёт User из callback (по telegram_id). Если нет — просит /start."""
    telegram_id = call.from_user.id
    user = User.objects.filter(telegram_id=telegram_id).first()
    if user:
        bot.answer_callback_query(call.id, f'👋 Привет, {user.first_name}!')
        return user
    logger.warning(f'Пользователь не найден: {telegram_id}')
    bot.answer_callback_query(call.id, '❌ Сначала напиши /start')
    bot.send_message(call.message.chat.id, '❌ Ты не зарегистрирован! Напиши /start')
    return None

@bot.callback_query_handler(func=lambda call: call.data == 'book')
def book_from_schedule_callback(call: CallbackQuery):
    """Кнопка «Записаться» из расписания -> book_command."""
    bot.answer_callback_query(call.id)
    user = get_user_from_callback(call)
    if not user:
        return
    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    book_command(fake_message)

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_book')
def cancel_book_callback(call: CallbackQuery):
    """Отмена выбора слота."""
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        '❌ Запись отменена.',
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=get_navigation_keyboard(),
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('book_'))
def confirm_booking_callback(call: CallbackQuery):
    """Выбор слота (book_YYYYMMDD_HHMM) -> проверки -> Booking."""
    bot.answer_callback_query(call.id, '⏳ Обрабатываю запрос...')
    user = get_user_from_callback(call)
    if not user:
        return
    parsed = parse_booking_callback_data(call.data)
    if not parsed:
        bot.answer_callback_query(call.id, '❌ Ошибка! Попробуй снова.')
        return
    dt, time_obj = parsed
    day = dt.weekday()

    # Слот существует?
    if not is_valid_slot(day, time_obj):
        bot.edit_message_text(
            f'❌ Слот {WEEKDAY_NAMES[day]} {time_obj.strftime("%H:%M")} не существует!',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
        )
        return

    # Уже записан?
    if Booking.objects.filter(
        user=user, date=dt, time=time_obj, is_active=True
    ).exists():
        bot.edit_message_text(
            f'❌ Ты уже записан на {WEEKDAY_NAMES[day]} {time_obj.strftime("%H:%M")}!',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
        )
        return

    # Есть места?
    booked_count = Booking.objects.filter(
        date=dt, time=time_obj, is_active=True
    ).count()
    if booked_count >= MAX_PEOPLE_PER_SLOT:
        bot.edit_message_text(
            f'😞 На {WEEKDAY_NAMES[day]} {time_obj.strftime("%H:%M")} мест больше нет.',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
        )
        return

    # Лимиты (1/день, 3/неделю, не прошлое)
    is_allowed, limit_message = check_booking_limits(user, dt)
    if not is_allowed:
        bot.edit_message_text(
            limit_message,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
            parse_mode='Markdown',
        )
        return

    # Создаём запись (уведомление в группу — раз в день, не здесь)
    try:
        Booking.objects.create(user=user, date=dt, time=time_obj, is_active=True)
        logger.info(f'Создана запись: {user} -> {dt} {time_obj}')
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'),
            InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'),
        )
        keyboard.add(InlineKeyboardButton('❓ Помощь', callback_data='nav_help'))
        bot.edit_message_text(
            f'✅ Ты записался!\n\n'
            f'📅 {WEEKDAY_NAMES[day]} {dt.strftime("%d.%m")}\n'
            f'⏰ {time_obj.strftime("%H:%M")}\n\n'
            f'Мест осталось: {MAX_PEOPLE_PER_SLOT - booked_count - 1}',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )
    except IntegrityError:
        bot.edit_message_text(
            '❌ Произошла ошибка. Возможно, ты уже записан.',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
        )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_booking')
def cancel_booking_callback(call: CallbackQuery):
    """Начинает отмену: если одна запись — сразу, если несколько — выбор."""
    bot.answer_callback_query(call.id)
    user = get_user_from_callback(call)
    if not user:
        return
    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)
    bookings = Booking.objects.filter(
        user=user, is_active=True,
        date__gte=week_start, date__lte=week_end,
    ).order_by('date', 'time')

    if not bookings:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton('📝 Записаться', callback_data='book'),
            InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'),
        )
        bot.edit_message_text(
            '📭 У тебя нет активных записей на текущую неделю.',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb,
        )
        return

    if len(bookings) == 1:
        booking = bookings.first()
        booking.is_active = False
        booking.save()
        logger.info(f'Отменена запись: {booking}')
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'),
            InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'),
        )
        keyboard.add(InlineKeyboardButton('❓ Помощь', callback_data='nav_help'))
        bot.edit_message_text(
            f'❌ Запись на {booking.date.strftime("%d.%m")} '
            f'{booking.time.strftime("%H:%M")} отменена.',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    for booking in bookings:
        date_str = booking.date.strftime('%Y%m%d')
        time_str = booking.time.strftime('%H%M')
        day_name = WEEKDAY_NAMES_SHORT[booking.date.weekday()]
        button_text = (
            f'{day_name} {booking.date.strftime("%d.%m")} '
            f'{booking.time.strftime("%H:%M")}'
        )
        keyboard.add(InlineKeyboardButton(
            button_text, callback_data=f'cancel_{date_str}_{time_str}',
        ))
    keyboard.add(
        InlineKeyboardButton('❌ Отмена', callback_data='cancel_cancel'),
        InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'),
    )
    bot.edit_message_text(
        'Выбери запись для отмены:',
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard,
    )


@bot.callback_query_handler(func=lambda call: call.data == 'cancel_cancel')
def cancel_cancel_callback(call: CallbackQuery):
    """Отмена отмены."""
    bot.answer_callback_query(call.id)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(
        call.message.chat.id,
        '❌ Отмена отменена. Твои записи сохранены.',
        reply_markup=get_navigation_keyboard(),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def confirm_cancel_callback(call: CallbackQuery):
    """Подтверждение отмены конкретной записи (cancel_YYYYMMDD_HHMM)."""
    bot.answer_callback_query(call.id)
    user = get_user_from_callback(call)
    if not user:
        return
    try:
        _, date_str, time_str = call.data.split('_')
        dt = datetime.strptime(date_str, '%Y%m%d').date()
        time_obj = datetime.strptime(time_str, '%H%M').time()
    except (ValueError, IndexError):
        bot.send_message(call.message.chat.id, '❌ Ошибка! Попробуй снова.')
        return
    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)
    if dt < week_start or dt > week_end:
        bot.edit_message_text(
            '❌ Эта запись не на текущей неделе.',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
        )
        return
    booking = Booking.objects.filter(
        user=user, date=dt, time=time_obj, is_active=True,
    ).first()
    if not booking:
        bot.edit_message_text(
            '❌ Запись не найдена или уже отменена.',
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_navigation_keyboard(),
        )
        return
    booking.is_active = False
    booking.save()
    logger.info(f'Отменена запись: {booking}')
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'),
        InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'),
    )
    keyboard.add(InlineKeyboardButton('❓ Помощь', callback_data='nav_help'))
    bot.edit_message_text(
        f'❌ Запись на {dt.strftime("%d.%m")} {time_obj.strftime("%H:%M")} отменена.',
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard,
    )


# --- ОТЗЫВ ---

@bot.callback_query_handler(func=lambda call: call.data == 'review')
def review_callback(call: CallbackQuery):
    """Кнопка «Отзыв» -> ждём текст (FSM, 1 шаг)."""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, '✍️ Напиши отзыв о работе бота:')
    bot.register_next_step_handler(msg, save_review)


def save_review(message):
    """Сохраняет отзыв из следующего сообщения."""
    user = get_user_from_message(message)
    if not user:
        return
    text = message.text.strip()
    if not text:
        bot.send_message(message.chat.id, '❌ Отзыв не может быть пустым')
        return
    Review.objects.create(user=user, text=text)
    bot.send_message(message.chat.id, '✅ Спасибо за отзыв!')


# --- ПРОФИЛЬ ---

@bot.callback_query_handler(func=lambda call: call.data == 'profile_edit_name')
def profile_edit_name(call: CallbackQuery):
    """Кнопка «Изменить имя» -> ждём новое имя (FSM, 1 шаг)."""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, 'Введи новое имя для расписания:')
    bot.register_next_step_handler(msg, save_display_name)


def save_display_name(message):
    """Сохраняет display_name из следующего сообщения."""
    user = get_user_from_message(message)
    if not user:
        return
    name = message.text.strip()
    if not name:
        bot.send_message(message.chat.id, '❌ Имя не может быть пустым')
        return
    user.display_name = name
    user.save()
    bot.send_message(message.chat.id, f'✅ Имя изменено: {name}')


# --- AIRSOFT ---

@bot.callback_query_handler(func=lambda call: call.data in ('airsoft_yes', 'airsoft_no'))
def airsoft_confirm(call: CallbackQuery):
    """Подтверждение/отказ airsoft. При «Да» — уведомление тренерам."""
    bot.answer_callback_query(call.id)
    user = get_user_from_callback(call)
    if not user:
        return
    confirmed = call.data == 'airsoft_yes'
    week_start = get_current_week_start()
    AirsoftConfirmation.objects.update_or_create(
        user=user, week_start=week_start,
        defaults={'confirmed': confirmed},
    )
    if confirmed:
        for trainer in get_trainers():
            try:
                bot.send_message(
                    trainer.telegram_id,
                    f'✅ {user.display_name} подтвердил участие в airsoft.',
                )
            except Exception as e:
                logger.error(f'Тренер {trainer}: {e}')
    bot.edit_message_text(
        '✅ Участие подтверждено' if confirmed else '❌ Участие отклонено',
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )


# --- РЕГИСТРАЦИЯ (уведомление админу) ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('reg_gender_'))
def reg_gender(call: CallbackQuery):
    """Админ ставит пол новому пользователю (reg_gender_{user_id}_{M/F})."""
    bot.answer_callback_query(call.id)
    _, _, user_id, gender = call.data.split('_')
    User.objects.filter(id=int(user_id)).update(gender=gender)
    bot.edit_message_text(
        f'✅ Пол: {gender}', call.message.chat.id, call.message.message_id,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('reg_airsoft_'))
def reg_airsoft(call: CallbackQuery):
    """Админ ставит is_airsoft_member новому пользователю (reg_airsoft_{user_id}_{1/0})."""
    bot.answer_callback_query(call.id)
    _, _, user_id, value = call.data.split('_')
    User.objects.filter(id=int(user_id)).update(
        is_airsoft_member=(value == '1')
    )
    bot.edit_message_text(
        f'✅ Airsoft: {value == "1"}', call.message.chat.id, call.message.message_id,
    )