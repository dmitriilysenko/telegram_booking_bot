from .core import bot, logger, GROUP_CHAT_ID, BOT_LINK
from .config import MAX_PEOPLE_PER_SLOT, VALID_SLOTS
from .scheduler import start_scheduler
from . import handlers  # noqa: F401  (регистрирует @bot.message_handler)
import logging
import telebot


telebot.logger.setLevel(logging.DEBUG)

def run_bot():
    """Запускает бота"""
    logger.info('🚀 Бот запущен!')
    scheduler = start_scheduler()
    logger.info(f'📊 Загружено {len(VALID_SLOTS)} слотов')
    logger.info(f'👥 Максимум человек на слот: {MAX_PEOPLE_PER_SLOT}')

    if GROUP_CHAT_ID:
        logger.info(f'📢 Уведомления в группу: включены (ID: {GROUP_CHAT_ID})')
    else:
        logger.warning('⚠️ Уведомления в группу: ОТКЛЮЧЕНЫ (GROUP_CHAT_ID не задан)')

    logger.info(f'🔗 Ссылка на бота: {BOT_LINK}')

    try:
        bot.infinity_polling(
            logger_level=logging.DEBUG,
            timeout=10,
            long_polling_timeout=5
        )
    except Exception as e:
        logger.error(f'❌ Ошибка при работе бота: {e}')
        raise
    finally:
        scheduler.shutdown()
        logger.info('🛑 Планировщик остановлен')