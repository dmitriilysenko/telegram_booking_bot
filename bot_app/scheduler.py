from datetime import datetime, time, timedelta

from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from django_apscheduler.jobstores import DjangoJobStore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from .models import Booking, User, AirsoftTraining, AirsoftConfirmation
from .core import bot, logger, GROUP_CHAT_ID, BOT_LINK, format_mention
from .config import (
    WEEKDAY_NAMES, BOOKING_OPEN_HOUR, SLOTS_BY_DAY,
)
from .services.schedule import (
    format_schedule_text, format_slot,
    get_current_week_start, get_week_range, get_slots_for_week,
)
from .services.airsoft import get_training_dt


_scheduler = None

CANCELLATION_DELAY_MINUTES = 10


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
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())

    training = AirsoftTraining.objects.filter(
        gender=gender, week_start=week_start,
    ).first()

    # Тренировка отменена → опрос не шлём (уведомление об отмене — отдельно)
    if not training or training.status == 'cancelled':
        logger.info(f'ℹ️ Airsoft {gender}: тренировка отменена/нет — опрос не шлём')
        return

    # Кто уже ответил (нажал ✅ или ❌) — исключаем
    answered_ids = AirsoftConfirmation.objects.filter(
        week_start=week_start, gender=gender,
    ).values_list('user_id', flat=True)

    users = User.objects.filter(
        is_airsoft_member=True, gender=gender,
    ).exclude(id__in=answered_ids)

    if not users.exists():
        logger.info(f'ℹ️ Airsoft {gender}: все уже ответили — пропускаем')
        return

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

def create_weekly_airsoft_trainings():
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    for gender in ('M', 'F'):
        _, created = AirsoftTraining.objects.get_or_create(
            gender=gender, week_start=week_start,
            defaults={'status': 'pending'},
        )
        if created:
            logger.info(f'🆕 AirsoftTraining: {gender} — {week_start}')


def send_airsoft_boys():
    send_airsoft_reminder('M')


def send_airsoft_girls():
    send_airsoft_reminder('F')

def schedule_cancellation_notification(
    gender: str, week_start, cancelled_by_telegram_id: int,
):
    """Ставит job через 10 минут после отмены."""
    if _scheduler is None:
        logger.error('⚠️ Планировщик не запущен — отмена не будет разослана')
        return
    run_at = timezone.now() + timedelta(minutes=CANCELLATION_DELAY_MINUTES)
    job_id = f'airsoft_cancel_{gender}_{week_start.isoformat()}'
    _scheduler.add_job(
        send_cancellation_notification,
        trigger=DateTrigger(run_date=run_at),
        args=[gender, week_start, cancelled_by_telegram_id],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f'⏳ Отложено уведомление об отмене {gender} на {run_at}')


def send_cancellation_notification(
    gender: str, week_start, cancelled_by_telegram_id: int,
):
    """Шлёт уведомление об отмене, если тренировка всё ещё cancelled."""
    training = AirsoftTraining.objects.filter(
        gender=gender, week_start=week_start,
    ).first()

    if not training or training.status != 'cancelled':
        logger.info(f'ℹ️ Airsoft {gender}: отмена отменена — уведомление не шлём')
        return

    trainers = User.objects.filter(is_trainer=True).exclude(
        telegram_id=cancelled_by_telegram_id,
    )
    members = User.objects.filter(is_airsoft_member=True, gender=gender)

    recipients = set(trainers.values_list('telegram_id', flat=True))
    recipients |= set(members.values_list('telegram_id', flat=True))

    if not recipients:
        logger.info(f'ℹ️ Airsoft {gender}: получателей нет — пропускаем')
        return

    dt = get_training_dt(week_start, gender)
    weekday = WEEKDAY_NAMES[dt.weekday()]
    gender_label = 'парней' if gender == 'M' else 'девушек'
    text = (
        f'❌ *Тренер отменил тренировку по airsoft*\n\n'
        f'Группа: {gender_label}\n'
        f'Когда: {weekday} {dt.strftime("%d.%m %H:%M")}'
    )

    for telegram_id in recipients:
        try:
            bot.send_message(telegram_id, text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f'❌ Уведомление об отмене {telegram_id}: {e}')

    logger.info(f'✅ Уведомление об отмене {gender} отправлено {len(recipients)}')

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
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_jobstore(DjangoJobStore(), 'default')

    # Разово при старте — подчистить накопленное
    deactivate_past_bookings()

    # Утренние слоты — одно уведомление в 11:00
    _scheduler.add_job(
        send_reminder_group,
        trigger=CronTrigger(hour=11, minute=0),
        args=[(time(11, 30), time(11, 45), time(12, 0))],
        id='reminder_morning',
        replace_existing=True,
    )
    # Вечерний слот — отдельно в 16:40
    _scheduler.add_job(
        send_reminder_group,
        trigger=CronTrigger(hour=16, minute=40),
        args=[(time(17, 10),)],
        id='reminder_evening',
        replace_existing=True,
    )

    # Дневное расписание
    _scheduler.add_job(
        send_daily_schedule,
        trigger=CronTrigger(hour=17, minute=0),
        id='daily_schedule',
        replace_existing=True,
    )

    # Гашение прошедших записей
    _scheduler.add_job(
        deactivate_past_bookings,
        trigger=CronTrigger(hour=0, minute=5),
        id='deactivate_past_bookings',
        replace_existing=True,
    )

    # Автосоздание airsoft-тренировок — понедельник, вместе с открытием записи
    _scheduler.add_job(
        create_weekly_airsoft_trainings,
        trigger=CronTrigger(day_of_week='mon', hour=BOOKING_OPEN_HOUR, minute=0),
        id='create_weekly_airsoft_trainings',
        replace_existing=True,
    )

    # Airsoft-опросы
    _scheduler.add_job(
        send_airsoft_boys,
        trigger=CronTrigger(day_of_week='fri', hour=12, minute=0),
        id='airsoft_boys',
        replace_existing=True,
    )
    _scheduler.add_job(
        send_airsoft_girls,
        trigger=CronTrigger(day_of_week='thu', hour=12, minute=0),
        id='airsoft_girls',
        replace_existing=True,
    )

    # Уведомление об открытии записи — понедельник
    _scheduler.add_job(
        send_booking_open_notification,
        trigger=CronTrigger(day_of_week='mon', hour=BOOKING_OPEN_HOUR, minute=0),
        id='booking_open_notification',
        replace_existing=True,
    )

    _scheduler.start()
    logger.info('✅ Планировщик запущен!')
    for job in _scheduler.get_jobs():
        logger.info(f'  📅 {job.id} — {job.trigger}')
    return _scheduler
