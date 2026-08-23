"""
Конфигурация расписания бота
"""

from datetime import time

MAX_PEOPLE_PER_SLOT = 2

MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

SLOT_1 = time(11, 10)
SLOT_2 = time(11, 30)
SLOT_3 = time(12, 0)
SLOT_4 = time(17, 10)

SLOTS_BY_DAY = {
    TUESDAY: [SLOT_1, SLOT_2, SLOT_3, SLOT_4],
    WEDNESDAY: [SLOT_1, SLOT_2, SLOT_3, SLOT_4],
    THURSDAY: [SLOT_1, SLOT_2, SLOT_3, SLOT_4],
    FRIDAY: [SLOT_1, SLOT_2, SLOT_3],
}

# Генерируем плоский список всех слотов для быстрых проверок
# Формат: [(day, time), (day, time), ...]
VALID_SLOTS = [
    (day, time_obj)
    for day, times in SLOTS_BY_DAY.items()
    for time_obj in times
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

# Сокращённые названия (для кнопок)
WEEKDAY_NAMES_SHORT = {
    MONDAY: 'Пн',
    TUESDAY: 'Вт',
    WEDNESDAY: 'Ср',
    THURSDAY: 'Чт',
    FRIDAY: 'Пт',
    SATURDAY: 'Сб',
    SUNDAY: 'Вс',
}


# ============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С КОНФИГУРАЦИЕЙ
# ============================================

def is_valid_slot(day: int, time_obj: time) -> bool:
    """
    Проверяет, существует ли такой слот в конфигурации

    Args:
        day: день недели (0-6)
        time_obj: объект time

    Returns:
        True если слот существует, иначе False
    """
    return (day, time_obj) in VALID_SLOTS


def get_available_slots_text() -> str:
    """
    Возвращает форматированный текст со списком всех слотов
    Используется для подсказок пользователю при ошибках

    Returns:
        Строка со списком слотов
    """
    lines = []
    for day, times in SLOTS_BY_DAY.items():
        day_name = WEEKDAY_NAMES[day]
        lines.append(f"\n{day_name}:")
        for time_obj in times:
            lines.append(f"  {time_obj.strftime('%H:%M')}")
    return "\n".join(lines)


def get_slots_summary() -> str:
    """
    Возвращает краткую сводку по слотам (для отладки)

    Returns:
        Строка со сводкой
    """
    total_slots = len(VALID_SLOTS)
    days_count = len(SLOTS_BY_DAY)
    return (
        f"Всего слотов: {total_slots}\n"
        f"Дней: {days_count}\n"
        f"Максимум мест на слот: {MAX_PEOPLE_PER_SLOT}"
    )


# ============================================
# ПРОВЕРКА КОНФИГУРАЦИИ ПРИ ЗАГРУЗКЕ
# ============================================

def validate_config():
    """
    Проверяет конфигурацию на корректность
    Вызывается автоматически при импорте
    """
    if not VALID_SLOTS:
        raise ValueError("❌ Конфигурация пуста! Добавьте хотя бы один слот.")

    for day in SLOTS_BY_DAY.keys():
        if day not in WEEKDAY_NAMES:
            raise ValueError(f"❌ День {day} отсутствует в WEEKDAY_NAMES")

    unique_slots = set(VALID_SLOTS)
    if len(unique_slots) != len(VALID_SLOTS):
        duplicates = [s for s in VALID_SLOTS if VALID_SLOTS.count(s) > 1]
        raise ValueError(f"❌ Найдены дубликаты слотов: {set(duplicates)}")

    print("✅ Конфигурация расписания загружена:")
    print(get_slots_summary())


# Автоматическая проверка при импорте
validate_config()