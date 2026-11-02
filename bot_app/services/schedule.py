from datetime import date, timedelta
from django.utils import timezone

from bot_app.models import Booking
from bot_app.core import BOT_LINK
from bot_app.config import (
    MAX_PEOPLE_PER_SLOT, VALID_SLOTS, WEEKDAY_NAMES, WEEKDAY_NAMES_SHORT
)


def get_current_week_start() -> date:
    """Возвращает дату понедельника текущей недели"""
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


def get_week_range(week_start: date) -> str:
    """Возвращает строку с диапазоном дат недели"""
    week_end = week_start + timedelta(days=6)
    return f"{week_start.strftime('%d.%m')} – {week_end.strftime('%d.%m')}"

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
    today = timezone.localdate()

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