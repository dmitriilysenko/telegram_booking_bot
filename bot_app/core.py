import logging
from django.conf import settings
from functools import lru_cache
from django.core.exceptions import ImproperlyConfigured
from telebot import TeleBot


logger = logging.getLogger(__name__)

GROUP_CHAT_ID = getattr(settings, 'TEST_GROUP_CHAT_ID', None)
BOT_LINK = getattr(settings, 'BOT_LINK', '')


@lru_cache(maxsize=1)
def get_bot():
    token = getattr(settings, 'BOT_TOKEN', None)
    if not token:
        raise ImproperlyConfigured('BOT_TOKEN не найден в .env')
    return TeleBot(token)

bot = get_bot()

def format_mention(user):
    """Форматирует упоминание пользователя для HTML-разметки"""
    if user.username:
        return f'@{user.username}'
    return f'{user.first_name} {user.last_name or ""}'.strip()

def is_admin(user):
    return bool(user and user.is_staff)

def get_trainers():
    from bot_app.models import User
    return User.objects.filter(is_trainer=True)

class FakeMessage:
    """Заглушка Message для вызова команд из callback'ов."""
    def __init__(self, chat_id, from_user):
        self.chat = type('obj', (object,), {'id': chat_id})
        self.from_user = from_user