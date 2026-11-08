from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from .models import Booking, User
from .core import bot, logger, GROUP_CHAT_ID, format_mention
from .config import WEEKDAY_NAMES
from .services.schedule import format_schedule_text


def send_reminder(slot_hour: int, slot_minute: int):
    if not GROUP_CHAT_ID:
        return
    today = timezone.localdate()
    bookings = Booking.objects.filter(
        date=today, time__hour=slot_hour, time__minute=slot_minute, is_active=True
    ).select_related('user')
    if not bookings:
        logger.info(f'ℹ️ Нет записей на {slot_hour:02d}:{slot_minute:02d}')
        return
    names = [format_mention(b.user) for b in bookings]
    day_name = WEEKDAY_NAMES[today.weekday()]
    slot_time = f'{slot_hour:02d}:{slot_minute:02d}'
    text = (
        f'⏰ Напоминание!\n\nЧерез 30 минут занятие:\n'
        f'📅 {day_name} {today.strftime("%d.%m")}\n⏰ {slot_time}\n\n'
        f'👤 Записаны: {", ".join(names)}'
    )
    try:
        bot.send_message(GROUP_CHAT_ID, text)
        logger.info(f'✅ Напоминание на {slot_time}')
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

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), 'default')

    deactivate_past_bookings()

    reminders = [
        (11, 0, 11, 30), (11, 30, 12, 0), (16, 40, 17, 10),
    ]
    for remind_h, remind_m, schedule_h, schedule_m in reminders:
        scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(hour=remind_h, minute=remind_m),
            args=[schedule_h, schedule_m],
            id=f'reminder_{remind_h:02d}_{remind_m:02d}',
            replace_existing=True,
        )

    scheduler.add_job(
        send_daily_schedule, trigger=CronTrigger(hour=17, minute=0),
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

    scheduler.start()
    logger.info('✅ Планировщик запущен!')
    for job in scheduler.get_jobs():
        logger.info(f'  📅 {job.id} — {job.trigger}')
    return scheduler
