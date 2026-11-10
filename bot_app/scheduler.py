from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import time

from .models import Booking, User
from .core import bot, logger, GROUP_CHAT_ID, format_mention, BOT_LINK
from .config import WEEKDAY_NAMES, BOOKING_OPEN_HOUR
from .services.schedule import format_schedule_text, get_current_week_start, \
    get_week_range


def send_reminder_group(slot_times: tuple):
    """
    Одно уведомление на несколько слотов.
    slot_times — кортеж time(h, m), например (time(11,30), time(11,45), time(12,0)).
    """
    if not GROUP_CHAT_ID:
        return
    today = timezone.localdate()
    day_name = WEEKDAY_NAMES[today.weekday()]

    lines = ['⏰ <b>Напоминание!</b>', f'📅 {day_name} {today.strftime("%d.%m")}', '']
    has_any = False

    for t in slot_times:
        bookings = Booking.objects.filter(
            date=today, time=t, is_active=True,
        ).select_related('user')
        if not bookings:
            continue
        has_any = True
        mentions = ', '.join(format_mention(b.user) for b in bookings)
        lines.append(mentions)
        lines.append(f'⏰ {t.strftime("%H:%M")}')
        lines.append('')

    if not has_any:
        logger.info(f'ℹ️ Нет записей на {[t.strftime("%H:%M") for t in slot_times]}')
        return

    text = '\n'.join(lines).strip()
    try:
        bot.send_message(GROUP_CHAT_ID, text, parse_mode='HTML')
        logger.info(f'✅ Напоминание на {[t.strftime("%H:%M") for t in slot_times]}')
    except Exception as e:
        logger.error(f'❌ {e}')

def send_daily_schedule():
    if not GROUP_CHAT_ID:
        return

    today = timezone.localdate()
    if today.weekday() >= 5:
        logger.info('ℹ️ Выходной — расписание не отправляем')
        return

    try:
        text = format_schedule_text(show_past=False)
        bot.send_message(GROUP_CHAT_ID, text, parse_mode='Markdown')
        logger.info('✅ Дневное расписание отправлено')
    except Exception as e:
        logger.error(f'❌ Расписание: {e}')


def send_airsoft_reminder(gender: str):
    users = User.objects.filter(is_airsoft_member=True, gender=gender)
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton('✅ Да', callback_data='airsoft_yes'),
        InlineKeyboardButton('❌ Нет', callback_data='airsoft_no'),
    )
    for user in users:
        try:
            bot.send_message(
                user.telegram_id,
                'Сегодня состоится тренировка по airsoft, подтверждаешь участие?',
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f'❌ {user}: {e}')


def send_airsoft_boys():
    send_airsoft_reminder('M')


def send_airsoft_girls():
    send_airsoft_reminder('F')

def deactivate_past_bookings() -> int:
    """
    Гасит is_active у записей, дата которых уже прошла.
    Возвращает количество погашенных записей.
    """
    today = timezone.localdate()
    updated = Booking.objects.filter(
        is_active=True,
        date__lt=today,
    ).update(is_active=False)
    if updated:
        logger.info(f'🧹 Погашено прошедших записей: {updated}')
    return updated

def send_booking_open_notification():
    """Уведомление в группу: запись на неделю открыта."""
    if not GROUP_CHAT_ID:
        return
    week_start = get_current_week_start()
    week_range = get_week_range(week_start)
    text = (
        f'🔔 *Запись открыта!*\n\n'
        f'📅 Неделя {week_range}\n'
        f'⏰ Записаться можно с {BOOKING_OPEN_HOUR}:00\n\n'
        f'✏️ {BOT_LINK}'
    )
    try:
        bot.send_message(GROUP_CHAT_ID, text, parse_mode='Markdown')
        logger.info('✅ Уведомление об открытии записи отправлено')
    except Exception as e:
        logger.error(f'❌ Уведомление об открытии записи: {e}')

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), 'default')

    deactivate_past_bookings()

    scheduler.add_job(
        send_reminder_group,
        trigger=CronTrigger(hour=11, minute=0),
        args=[(time(11, 30), time(11, 45), time(12, 0))],
        id='reminder_morning',
        replace_existing=True,
    )

    scheduler.add_job(
        send_reminder_group,
        trigger=CronTrigger(hour=16, minute=40),
        args=[(time(17, 10),)],
        id='reminder_evening',
        replace_existing=True,
    )

    scheduler.add_job(
        send_daily_schedule, trigger=CronTrigger(hour=17, minute=30),
        id='daily_schedule', replace_existing=True,
    )
    scheduler.add_job(
        deactivate_past_bookings,
        trigger=CronTrigger(hour=0, minute=5),
        id='deactivate_past_bookings',
        replace_existing=True,
    )
    scheduler.add_job(
        send_airsoft_boys, trigger=CronTrigger(day_of_week='fri', hour=12, minute=0),
        id='airsoft_boys', replace_existing=True,
    )
    scheduler.add_job(
        send_airsoft_girls, trigger=CronTrigger(day_of_week='thu', hour=12, minute=0),
        id='airsoft_girls', replace_existing=True,
    )
    scheduler.add_job(
        send_booking_open_notification,
        trigger=CronTrigger(day_of_week='mon', hour=BOOKING_OPEN_HOUR, minute=0),
        id='booking_open_notification',
        replace_existing=True,
    )

    scheduler.start()
    logger.info('✅ Планировщик запущен!')
    for job in scheduler.get_jobs():
        logger.info(f'  📅 {job.id} — {job.trigger}')
    return scheduler
