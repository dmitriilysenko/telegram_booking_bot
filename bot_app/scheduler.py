"""
Планировщик уведомлений на apscheduler с хранением в БД
"""

from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore

from .models import Booking
from .core import bot, logger, GROUP_CHAT_ID, format_mention
from .config import WEEKDAY_NAMES


def send_reminder(slot_hour: int, slot_minute: int):
    """Отправляет напоминание, если есть записи"""
    if not GROUP_CHAT_ID:
        return

    today = timezone.localdate()

    bookings = Booking.objects.filter(
        date=today,
        time__hour=slot_hour,
        time__minute=slot_minute,
        is_active=True
    ).select_related('user')

    if not bookings:
        logger.info(f"ℹ️ Нет записей на {slot_hour:02d}:{slot_minute:02d}")
        return

    names = []
    for booking in bookings:
        names.append(format_mention(booking.user))

    day_name = WEEKDAY_NAMES[today.weekday()]
    slot_time = f"{slot_hour:02d}:{slot_minute:02d}"

    text = (
        f"⏰ Напоминание!\n\n"
        f"Через 30 минут занятие:\n"
        f"📅 {day_name} {today.strftime('%d.%m')}\n"
        f"⏰ {slot_time}\n\n"
        f"👤 Записаны: {', '.join(names)}"
    )

    try:
        bot.send_message(GROUP_CHAT_ID, text)
        logger.info(f"✅ Напоминание отправлено на {slot_time}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")


def start_scheduler():
    """Запускает планировщик с задачами на каждый день"""
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # Три задачи — каждый день в нужное время
    # (время_уведомления, час_слота, минута_слота)
    reminders = [
        (11, 0, 11, 30),
        (11, 30, 12, 0),
        (16, 40, 17, 10),
    ]

    for remind_h, remind_m, schedule_h, schedule_m in reminders:
        scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(hour=remind_h, minute=remind_m),
            args=[schedule_h, schedule_m],
            id=f"reminder_{remind_h:02d}_{remind_m:02d}",
            replace_existing=True,
        )

    scheduler.start()
    logger.info("✅ Планировщик запущен!")

    # Показываем, какие задачи запланированы
    jobs = scheduler.get_jobs()
    for job in jobs:
        logger.info(f"  📅 {job.id} — {job.trigger}")
    return scheduler
