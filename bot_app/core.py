import logging
from django.conf import settings
from functools import lru_cache
from django.core.exceptions import ImproperlyConfigured
from telebot import TeleBot


logger = logging.getLogger(__name__)
BOT_TOKEN = getattr(settings, 'BOT_TOKEN', None)


@lru_cache(maxsize=1)
def get_bot():
    token = getattr(settings, 'BOT_TOKEN', None)
    if not token:
        raise ImproperlyConfigured('BOT_TOKEN не найден в .env')
    return TeleBot(token)

bot = get_bot()

GROUP_CHAT_ID = getattr(settings, 'GROUP_CHAT_ID', None)
BOT_LINK = getattr(settings, 'BOT_LINK', '')

def format_mention(user) -> str:
    """
    Форматирует упоминание пользователя для HTML-разметки
    """
    if user.username:
        mention = f"@{user.username}"
    else:
        mention = f"{user.first_name} {user.last_name or ''}".strip()
    return mention

class FakeMessage:
    """Заглушка Message для вызова команд из callback'ов."""
    def __init__(self, chat_id, from_user):
        self.chat = type('obj', (object,), {'id': chat_id})
        self.from_user = from_user