from datetime import timedelta, datetime

from django.utils import timezone

from bot_app.models import AirsoftTraining, AirsoftConfirmation
from bot_app.config import WEEKDAY_NAMES


STATUS_ICONS = {
    'pending': '⏳',
    'confirmed': '✅',
    'cancelled': '❌',
}

def _training_dt(week_start, gender):
    """aware datetime тренировки: девушки — чт 17:20, парни — пт 16:20."""
    dt = week_start + timedelta(days=3 if gender == 'F' else 4)
    time_str = '17:20' if gender == 'F' else '16:20'
    hour, minute = map(int, time_str.split(':'))
    return timezone.make_aware(
        datetime.combine(dt, datetime.min.time()).replace(
            hour=hour, minute=minute
        )
    )

def get_training_dt(week_start, gender):
    """Публичная обёртка: aware datetime тренировки."""
    return _training_dt(week_start, gender)

def format_airsoft_text(user):
    """
    Возвращает (text, has_upcoming).
    has_upcoming=False — если обе тренировки на текущей неделе уже прошли.
    """
    now = timezone.localtime(timezone.now())
    today = now.date()
    week_start = today - timedelta(days=today.weekday())

    lines = ['🎯 *Airsoft-тренировки*\n']
    has_upcoming = False

    for gender, title in (('F', 'Девушки'), ('M', 'Парни')):
        slot_dt = _training_dt(week_start, gender)
        if slot_dt <= now:
            continue
        has_upcoming = True
        dt = slot_dt.date()
        time_str = slot_dt.strftime('%H:%M')

        training = AirsoftTraining.objects.filter(
            gender=gender, week_start=week_start
        ).first()
        if training:
            status = f'{STATUS_ICONS.get(training.status, "")} {training.get_status_display()}'
        else:
            status = '⏳ Тренировка не подтверждена'

        confirmed = AirsoftConfirmation.objects.filter(
            gender=gender, week_start=week_start, confirmed=True
        ).select_related('user')
        declined = AirsoftConfirmation.objects.filter(
            gender=gender, week_start=week_start, confirmed=False
        ).select_related('user')

        lines.append(f'*{title}*')
        lines.append(f'{WEEKDAY_NAMES[dt.weekday()]} {dt.strftime("%d.%m")} — {time_str}')
        lines.append(f'_{status}_')
        lines.append('Подтвердили участие:')
        lines.extend(
            [f'{i}. {c.user.display_name}' for i, c in enumerate(confirmed, 1)] or ['—']
        )
        lines.append('Не смогут участвовать:')
        lines.extend(
            [f'{i}. {c.user.display_name}' for i, c in enumerate(declined, 1)] or ['—']
        )
        lines.append('')

    if not has_upcoming:
        lines.append('📭 На этой неделе тренировок больше нет.')
        lines.append('Следующее расписание появится позже.')

    return '\n'.join(lines), has_upcoming