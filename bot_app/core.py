import logging
from django.conf import settings
from functools import lru_cache
from django.core.exceptions import ImproperlyConfigured
from telebot import TeleBot, apihelper
from telebot.handler_backends import BaseMiddleware


logger = logging.getLogger(__name__)

GROUP_CHAT_ID = getattr(settings, 'GROUP_CHAT_ID', None)
BOT_LINK = getattr(settings, 'BOT_LINK', '')


@lru_cache(maxsize=1)
def get_bot():
    token = getattr(settings, 'BOT_TOKEN', None)
    if not token:
        raise ImproperlyConfigured('BOT_TOKEN не найден в .env')
    return TeleBot(token, use_class_middlewares=True)

bot = get_bot()

class FsmResetMiddleware(BaseMiddleware):
    def __init__(self):
        self.update_types = ['callback_query']
        super().__init__()
    def pre_process(self, call, data):
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        return None
    def post_process(self, call, data, exception):
        return None

bot.setup_middleware(FsmResetMiddleware())

def format_mention(user):
    """Упоминание через HTML-ссылку — работает и без username."""
    name = user.display_name or user.first_name or f'ID {user.telegram_id}'
    return f'<a href="tg://user?id={user.telegram_id}">{name}</a>'

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