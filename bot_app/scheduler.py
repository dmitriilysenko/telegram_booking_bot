"""
Планировщик задач (APScheduler + DjangoJobStore).

Джобы:
- reminder_checker           — каждые 5 мин: напоминание за 25–35 мин до якорного слота (группа слотов одним сообщением)
- daily_schedule             — 17:30: расписание в группу
- deactivate_past_bookings   — каждые 5 мин: гасит is_active у записей, время которых наступило
- create_weekly_airsoft      — пн 09:00: создаёт AirsoftTraining на текущую неделю
- booking_open_notification  — пн 09:00: уведомление «Запись открыта!»
- airsoft_boys               — пт 12:00: опрос парней
- airsoft_girls              — чт 12:00: опрос девушек
- + отложенные job'ы отмены airsoft (DateTrigger, создаются из callbacks)
"""

from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from django.db.models import Q
from django_apscheduler.jobstores import DjangoJobStore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from .models import Booking, User, AirsoftTraining, AirsoftConfirmation
from .core import bot, logger, GROUP_CHAT_ID, BOT_LINK, format_mention
from .config import (
    WEEKDAY_NAMES, BOOKING_OPEN_HOUR, SLOTS_BY_DAY,
)
from .services.schedule import (
    format_schedule_text,
    get_current_week_start, get_week_range,
)
from .services.airsoft import get_training_dt


_scheduler = None
CANCELLATION_DELAY_MINUTES = 10


# ============================================================
# НАПОМИНАНИЯ О СЛОТАХ (винтовки)
# ============================================================

def send_reminder_group(slot_times: tuple):
    """
    Отправляет ОДНО сообщение на группу слотов.
    slot_times — кортеж time(h, m), например (11:30, 11:45, 12:00).
    Внутри фильтрует только те слоты, на которые есть активные записи.
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
        logger.error(f'❌ Напоминание: {e}')


def _group_slot_times(slot_times: tuple, max_gap_minutes: int = 60) -> list:
    """
    Группирует слоты дня: соседние слоты с разницей ≤ max_gap минут — в одну группу.
    Пример: (11:30, 11:45, 12:00, 16:10) → [(11:30, 11:45, 12:00), (16:10,)]
    Первый слот группы — «якорь», по нему считается время напоминания.
    """
    if not slot_times:
        return []

    times = sorted(slot_times)
    groups = []
    current = [times[0]]

    for t in times[1:]:
        prev = current[-1]
        gap = (t.hour * 60 + t.minute) - (prev.hour * 60 + prev.minute)
        if gap <= max_gap_minutes:
            current.append(t)
        else:
            groups.append(tuple(current))
            current = [t]

    groups.append(tuple(current))
    return groups


def check_upcoming_slots_and_remind():
    """
    Каждые 5 минут:
    для каждой группы слотов дня проверяет, не пора ли слать напоминание
    (за 25–35 минут до ПЕРВОГО слота группы).
    Защита от дублей — через cache: ключ по дате+времени якоря.
    """
    now = timezone.localtime(timezone.now())
    today = now.date()
    today_weekday = today.weekday()

    slot_times = SLOTS_BY_DAY.get(today_weekday, ())
    if not slot_times:
        return

    for group in _group_slot_times(slot_times):
        anchor = group[0]
        anchor_dt = timezone.make_aware(datetime.combine(today, anchor))
        delta_minutes = (anchor_dt - now).total_seconds() / 60

        # Напоминание — за 25–35 минут до якоря
        if not (25 <= delta_minutes <= 35):
            continue

        # Защита от повторной отправки
        reminder_key = f'reminder_sent_{today.isoformat()}_{anchor.strftime("%H%M")}'
        if cache.get(reminder_key):
            logger.debug(f'⏭ {reminder_key}: уже отправлено')
            continue

        logger.info(
            f'⏰ Напоминание группа {[t.strftime("%H:%M") for t in group]} '
            f'(до якоря {int(delta_minutes)} мин)'
        )
        send_reminder_group(group)
        cache.set(reminder_key, 1, timeout=60 * 60)


# ============================================================
# РАСПИСАНИЕ (винтовки)
# ============================================================

def send_daily_schedule():
    """17:30 — расписание в группу (только Пн–Пт)."""
    if not GROUP_CHAT_ID:
        return

    today = timezone.localdate()
    if today.weekday() >= 4:
        logger.info('ℹ️ Выходной/пятница — расписание не отправляем')
        return

    try:
        text = format_schedule_text(show_past=False)
        bot.send_message(GROUP_CHAT_ID, text, parse_mode='Markdown')
        logger.info('✅ Дневное расписание отправлено')
    except Exception as e:
        logger.error(f'❌ Расписание: {e}')


def deactivate_past_bookings() -> int:
    """
    Гасит is_active у записей, время которых уже наступило:
    - date < today
    - date == today и time <= now.time()
    Возвращает количество погашенных.
    """

    now = timezone.localtime(timezone.now())
    today = now.date()
    current_time = now.time()

    updated = Booking.objects.filter(
        is_active=True,
    ).filter(
        Q(date__lt=today) |
        Q(date=today, time__lte=current_time)
    ).update(is_active=False)

    if updated:
        logger.info(f'🧹 Погашено прошедших записей: {updated} (до {current_time.strftime("%H:%M")})')
    return updated


# ============================================================
# AIRSOFT
# ============================================================

def send_airsoft_reminder(gender: str):
    """
    Опрос участников группы (gender) о подтверждении airsoft на текущую неделю.
    Не шлём, если тренировка отменена или уже все ответили.
    """
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())

    training = AirsoftTraining.objects.filter(
        gender=gender, week_start=week_start,
    ).first()

    if not training or training.status == 'cancelled':
        logger.info(f'ℹ️ Airsoft {gender}: тренировка отменена/нет — опрос не шлём')
        return

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
            logger.error(f'❌ Airsoft {user}: {e}')


def create_weekly_airsoft_trainings():
    """Пн 09:00 — создаёт AirsoftTraining(pending) на текущую неделю для M и F."""
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
    """Ставит DateTrigger через 10 минут после отмены тренировки."""
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


# ============================================================
# ОТКРЫТИЕ ЗАПИСИ
# ============================================================

def send_booking_open_notification():
    """Пн 09:00 — уведомление в группу, что запись открыта."""
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


# ============================================================
# ЗАПУСК ПЛАНИРОВЩИКА
# ============================================================

def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_jobstore(DjangoJobStore(), 'default')

    # Разово при старте — подчистить накопленное
    deactivate_past_bookings()

    # Напоминания о слотах — каждые 5 минут (динамически, по группам)
    _scheduler.add_job(
        check_upcoming_slots_and_remind,
        trigger=CronTrigger(minute='*/5'),
        id='reminder_checker',
        replace_existing=True,
    )

    # Дневное расписание — 17:30
    _scheduler.add_job(
        send_daily_schedule,
        trigger=CronTrigger(hour=17, minute=30),
        id='daily_schedule',
        replace_existing=True,
    )

    # Гашение прошедших записей — каждые 5 минут
    _scheduler.add_job(
        deactivate_past_bookings,
        trigger=CronTrigger(minute='*/5'),
        id='deactivate_past_bookings',
        replace_existing=True,
    )

    # Автосоздание airsoft-тренировок — Пн 09:00
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

    # Уведомление об открытии записи — Пн 09:00
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