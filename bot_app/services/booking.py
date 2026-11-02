from datetime import date, datetime, timedelta

from bot_app.models import Booking
from bot_app.core import bot, logger, GROUP_CHAT_ID
from bot_app.config import WEEKDAY_NAMES, BOOKING_OPEN_HOUR
from .schedule import get_current_week_start
from .schedule import format_schedule_text


def check_booking_limits(user, dt: date) -> tuple:
    """
    Проверяет ограничения для пользователя:
    - Нельзя записаться на прошлое
    - Нельзя записаться ранее BOOKING_OPEN_HOUR понедельника
    - Не более 1 записи в день
    - Не более 3 записей в неделю

    Возвращает (is_allowed, message)
    """
    # Проверка: нельзя записаться на прошлое
    today = date.today()
    if dt < today:
        return False, "❌ Нельзя записаться на прошедшую дату! Выбери будущую дату."

    # Проверка: нельзя записаться ранее BOOKING_OPEN_HOUR понедельника
    week_start = get_current_week_start()
    monday_open = datetime.combine(week_start, datetime.min.time()).replace(hour=BOOKING_OPEN_HOUR, minute=0)
    now = datetime.now()

    if now < monday_open:
        time_left = monday_open - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        return False, (
            f"❌ Запись на неделю открывается в *понедельник в {BOOKING_OPEN_HOUR}:00*!\n"
            f"⏳ Осталось: {hours} ч {minutes} мин\n\n"
            f"📅 Следующая неделя откроется: {week_start.strftime('%d.%m')} в {BOOKING_OPEN_HOUR}:00"
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