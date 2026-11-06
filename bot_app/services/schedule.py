from datetime import date, datetime, timedelta
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
    return f'{week_start.strftime("%d.%m")} – {week_end.strftime("%d.%m")}'

def format_slot(slot: dict) -> str:
    time_str = slot['time'].strftime('%H:%M')
    if slot['is_full']:
        return f'🔴 {time_str} — мест нет'
    if slot['free_slots'] == 1:
        return f'🟡 {time_str} — доступно 1 место'
    return f'🟢 {time_str} — доступно {slot["free_slots"]} места'

def get_slots_for_week(week_start: date = None, show_past: bool = False) -> list:
    if week_start is None:
        week_start = get_current_week_start()

    now = timezone.localtime(timezone.now())
    result = []
    for day, time_obj in VALID_SLOTS:
        days_ahead = day - week_start.weekday()
        if days_ahead < 0:
            days_ahead += 7
        dt = week_start + timedelta(days=days_ahead)

        slot_dt = timezone.make_aware(datetime.combine(dt, time_obj))
        if not show_past and slot_dt <= now:
            continue

        bookings = Booking.objects.filter(
            date=dt, time=time_obj, is_active=True
        ).select_related('user')
        booked_count = bookings.count()
        is_full = booked_count >= MAX_PEOPLE_PER_SLOT
        result.append({
            'date': dt, 'time': time_obj, 'day': day,
            'day_name': WEEKDAY_NAMES[day],
            'day_name_short': WEEKDAY_NAMES_SHORT[day],
            'booked_count': booked_count,
            'max_people': MAX_PEOPLE_PER_SLOT,
            'free_slots': MAX_PEOPLE_PER_SLOT - booked_count,
            'is_full': is_full,
            'is_available': not is_full,
            'names': [b.user.display_name or b.user.first_name for b in bookings],
        })
    return result


def format_schedule_text(week_start: date = None) -> str:
    if week_start is None:
        week_start = get_current_week_start()
    week_range = get_week_range(week_start)
    slots = get_slots_for_week(week_start, show_past=True)

    grouped = {}
    for slot in slots:
        grouped.setdefault(slot['day_name'], []).append(slot)

    text = f'📅 *Расписание на неделю {week_range}*\n\n'
    for day_name, day_slots in grouped.items():
        text += f'📍 *{day_name}*\n'
        for slot in day_slots:
            line = f'  {format_slot(slot)}'
            if slot['names']:
                line += f' — {", ".join(slot["names"])}'
            text += line + '\n'
        text += '\n'
    text += f'\n✏️ Записаться: {BOT_LINK}'
    return text
