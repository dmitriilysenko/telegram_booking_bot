from datetime import timedelta

from django.utils import timezone

from bot_app.models import AirsoftTraining, AirsoftConfirmation
from bot_app.config import WEEKDAY_NAMES


def _training_date(week_start, gender):
    """Девушки — четверг (3), парни — пятница (4)."""
    return week_start + timedelta(days=3 if gender == 'F' else 4)


def format_airsoft_text(user) -> str:
    """Текст: обе тренировки (чт/пт), статус, кто подтвердил/отказался."""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())

    lines = ['🎯 *Airsoft-тренировки*\n']
    for gender, title in (('F', 'Девушки'), ('M', 'Парни')):
        dt = _training_date(week_start, gender)
        training = AirsoftTraining.objects.filter(
            gender=gender, week_start=week_start
        ).first()
        status = (
            training.get_status_display()
            if training else 'Тренировка не подтверждена'
        )
        time_str = '17:20' if gender == 'F' else '16:20'

        confirmed = AirsoftConfirmation.objects.filter(
            gender=gender, week_start=week_start, confirmed=True
        ).select_related('user')
        declined = AirsoftConfirmation.objects.filter(
            gender=gender, week_start=week_start, confirmed=False
        ).select_related('user')

        confirmed_names = [
            f'{i}. {c.user.display_name}'
            for i, c in enumerate(confirmed, 1)
        ]
        declined_names = [
            f'{i}. {c.user.display_name}'
            for i, c in enumerate(declined, 1)
        ]

        lines.append(f'*{title}*')
        lines.append(
            f'{WEEKDAY_NAMES[dt.weekday()]} {dt.strftime("%d.%m")} — {time_str}'
        )
        lines.append(f'_{status}_')
        lines.append('Подтвердили участие:')
        lines.extend(confirmed_names or ['—'])
        lines.append('Не смогут участвовать:')
        lines.extend(declined_names or ['—'])
        lines.append('')

    return '\n'.join(lines)