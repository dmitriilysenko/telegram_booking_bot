from telebot.types import Message, CallbackQuery

from bot_app.core import bot, FakeMessage
from bot_app.keyboards import get_navigation_keyboard
from .commands import my_bookings_command, schedule_command, help_command


@bot.callback_query_handler(func=lambda call: call.data == "nav_my_bookings")
def nav_my_bookings_callback(call: CallbackQuery):
    """Навигация в /my_bookings"""
    bot.answer_callback_query(call.id)
    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    my_bookings_command(fake_message)


@bot.callback_query_handler(func=lambda call: call.data == "nav_schedule")
def nav_schedule_callback(call: CallbackQuery):
    """Навигация в /schedule"""
    bot.answer_callback_query(call.id)
    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    schedule_command(fake_message)


@bot.callback_query_handler(func=lambda call: call.data == "nav_help")
def nav_help_callback(call: CallbackQuery):
    """Навигация в /help"""
    bot.answer_callback_query(call.id)
    fake_message = FakeMessage(call.message.chat.id, call.from_user)
    help_command(fake_message)


@bot.message_handler(func=lambda message: True)
def echo_all(message: Message):
    """Ответ на любое сообщение, не являющееся командой"""
    keyboard = get_navigation_keyboard()
    bot.send_message(
        message.chat.id,
        "😅 Я не понимаю это сообщение\n"
        "Используй кнопки ниже для навигации:",
        reply_markup=keyboard
    )


