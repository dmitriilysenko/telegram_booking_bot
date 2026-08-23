"""
Обработка исключений и проверка конфигурации
"""

import os
from django.core.exceptions import ImproperlyConfigured


def get_env_variable(var_name: str, default=None, required=True):
    """
    Получает переменную из окружения с проверкой

    Args:
        var_name: имя переменной
        default: значение по умолчанию (если не required)
        required: обязательна ли переменная

    Returns:
        Значение переменной

    Raises:
        ImproperlyConfigured: если переменная обязательна и не найдена
    """
    value = os.getenv(var_name, default)

    if required and value is None:
        raise ImproperlyConfigured(
            f"❌ Переменная '{var_name}' не найдена в .env!\n"
            f"Добавь {var_name}=значение в файл .env"
        )

    return value


def validate_bot_settings():
    """
    Проверяет настройки бота при запуске.
    Вызывается из runbot.py, а не из settings.py.
    """
    from django.conf import settings

    errors = []
    warnings = []

    # 1. Проверяем BOT_TOKEN
    if not getattr(settings, 'BOT_TOKEN', None):
        errors.append("BOT_TOKEN не найден в .env")

    # 2. Проверяем SECRET_KEY
    if not getattr(settings, 'SECRET_KEY', None):
        errors.append("SECRET_KEY не найден в .env")

    # 3. Проверяем DEBUG в продакшене
    if not getattr(settings, 'DEBUG', True):
        warnings.append("⚠️ DEBUG = False — статика может не работать")

    # 4. Проверяем GROUP_CHAT_ID
    group_id = getattr(settings, 'GROUP_CHAT_ID', None)
    if group_id:
        try:
            int(group_id)
        except (ValueError, TypeError):
            errors.append(f"GROUP_CHAT_ID должен быть числом, получено: {group_id}")
    else:
        warnings.append("⚠️ GROUP_CHAT_ID не задан — уведомления в группу не будут работать")

    # 5. Проверяем BOT_LINK
    if not getattr(settings, 'BOT_LINK', None):
        warnings.append("⚠️ BOT_LINK не задан — ссылка на бота не будет работать")

    # Выводим результаты
    if errors:
        error_msg = "❌ Ошибки в настройках бота:\n" + "\n".join(f"  • {e}" for e in errors)
        raise ImproperlyConfigured(error_msg)

    if warnings:
        print("⚠️ Предупреждения:")
        for w in warnings:
            print(f"  {w}")

    print("✅ Настройки бота проверены успешно!")
    return True