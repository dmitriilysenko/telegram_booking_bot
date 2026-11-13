from datetime import time

MAX_PEOPLE_PER_SLOT = 2

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)

SLOTS_BY_DAY = {
    TUESDAY: (time(11, 30), time(11, 45), time(12, 0), time(17, 10)),
    THURSDAY: (time(11, 30), time(11, 45), time(12, 0), time(17, 10)),
    FRIDAY: (time(11, 30), time(11, 45), time(12, 0), time(16, 10)),
}

VALID_SLOTS = [
    (day, time_obj)
    for day, times in SLOTS_BY_DAY.items()
    for time_obj in times
]

HIDDEN_SLOTS = [
    (date(2026, 11, 14), time(16, 10)),   # только 14.11
]

WEEKDAY_NAMES = {
    MONDAY: 'Понедельник',
    TUESDAY: 'Вторник',
    WEDNESDAY: 'Среда',
    THURSDAY: 'Четверг',
    FRIDAY: 'Пятница',
    SATURDAY: 'Суббота',
    SUNDAY: 'Воскресенье',
}

WEEKDAY_NAMES_SHORT = {
    MONDAY: 'Пн',
    TUESDAY: 'Вт',
    WEDNESDAY: 'Ср',
    THURSDAY: 'Чт',
    FRIDAY: 'Пт',
    SATURDAY: 'Сб',
    SUNDAY: 'Вс',
}
BOOKING_OPEN_HOUR = 9


def is_valid_slot(day: int, time_obj: time) -> bool:
    """Проверяет, существует ли такой слот в конфигурации."""
    return (day, time_obj) in VALID_SLOTS

def get_available_slots_text() -> str:
    """
    Возвращает форматированный текст со списком всех слотов
    Используется для подсказок пользователю при ошибках
    """

    lines = []
    for day, times in SLOTS_BY_DAY.items():
        lines.append(f'\n{WEEKDAY_NAMES[day]}:')
        for t in times:
            lines.append(f'  {t.strftime("%H:%M")}')
    return '\n'.join(lines)


def get_slots_summary() -> str:
    return (
        f'Всего слотов: {len(VALID_SLOTS)}\n'
        f'Дней: {len(SLOTS_BY_DAY)}\n'
        f'Максимум мест на слот: {MAX_PEOPLE_PER_SLOT}'
    )

def validate_config():
    if not VALID_SLOTS:
        raise ValueError('❌ Конфигурация пуста!')
    for day in SLOTS_BY_DAY:
        if day not in WEEKDAY_NAMES:
            raise ValueError(f'❌ День {day} отсутствует в WEEKDAY_NAMES')
    unique = set(VALID_SLOTS)
    if len(unique) != len(VALID_SLOTS):
        raise ValueError('❌ Дубликаты слотов')

# Автоматическая проверка при импорте
validate_config()