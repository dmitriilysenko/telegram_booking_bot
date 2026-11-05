from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_navigation_keyboard(
        show_my_bookings: bool = True,
        show_schedule: bool = True,
        show_main: bool = True,
        show_profile: bool = True,
        show_review: bool = True,
        show_book: bool = True,
        show_airsoft: bool = True
) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    if show_my_bookings:
        buttons.append(InlineKeyboardButton('📋 Мои записи', callback_data='nav_my_bookings'))
    if show_book:
        buttons.append(InlineKeyboardButton('📝 Записаться', callback_data='book'))
    if show_schedule:
        buttons.append(InlineKeyboardButton('📅 Расписание', callback_data='nav_schedule'))
    if show_airsoft:
        buttons.append(InlineKeyboardButton('🎯 Airsoft', callback_data='airsoft'))
    if show_profile:
        buttons.append(InlineKeyboardButton('👤 Кабинет', callback_data='nav_profile'))
    if show_main:
        buttons.append(InlineKeyboardButton('🏠 Главное меню', callback_data='nav_main'))
    if show_review:
        buttons.append(InlineKeyboardButton('✍️ Отзыв', callback_data='review'))
    keyboard.add(*buttons)
    return keyboard

def get_airsoft_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('✅ Подтвердить участие', callback_data='airsoft_yes'),
        InlineKeyboardButton('❌ Не смогу участвовать', callback_data='airsoft_no'),
    )
    kb.add(InlineKeyboardButton('🏠 Главное меню', callback_data='nav_main'))
    return kb

def get_trainer_airsoft_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('👧 Девушки, Чт', callback_data='trainer_F'),
        InlineKeyboardButton('👦 Парни, Пт', callback_data='trainer_M'),
    )
    kb.add(InlineKeyboardButton('🏠 Главное меню', callback_data='nav_main'))
    return kb