from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_navigation_keyboard(show_my_bookings: bool = True, show_schedule: bool = True, show_help: bool = True):
    """
    Создаёт навигационную клавиатуру с кнопками
    """
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []

    if show_my_bookings:
        buttons.append(InlineKeyboardButton("📋 Мои записи", callback_data="nav_my_bookings"))
    if show_schedule:
        buttons.append(InlineKeyboardButton("📅 Расписание", callback_data="nav_schedule"))
    if show_help:
        buttons.append(InlineKeyboardButton("❓ Помощь", callback_data="nav_help"))

    keyboard.add(*buttons)
    return keyboard