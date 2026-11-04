from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_navigation_keyboard(
        show_my_bookings: bool = True,
        show_schedule: bool = True,
        show_help: bool = True,
        show_profile: bool = True,
        show_review: bool = True
) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    if show_my_bookings:
        buttons.append(InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'))
    if show_schedule:
        buttons.append(InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'))
    if show_profile:
        buttons.append(InlineKeyboardButton('👤 Кабинет', callback_data='nav_profile'))
    if show_help:
        buttons.append(InlineKeyboardButton('❓ Помощь', callback_data='nav_help'))
    if show_review:
        buttons.append(InlineKeyboardButton('✍️ Отзыв', callback_data='review'))
    keyboard.add(*buttons)
    return keyboard