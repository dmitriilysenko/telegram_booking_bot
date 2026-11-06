from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_navigation_keyboard(
        show_my_bookings: bool = True,
        show_schedule: bool = True,
        show_main: bool = True,
        show_profile: bool = True,
        show_review: bool = True,
        show_book: bool = True,
        show_airsoft: bool = True,
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


def get_airsoft_member_keyboard() -> InlineKeyboardMarkup:
    """Участник: подтвердить/отказаться (группа — по user.gender)."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton('✅ Подтвердить участие', callback_data='airsoft_yes'),
        InlineKeyboardButton('❌ Не смогу участвовать', callback_data='airsoft_no'),
        InlineKeyboardButton('🏠 Главное меню', callback_data='nav_main'),
    )
    return kb


def get_airsoft_trainer_keyboard() -> InlineKeyboardMarkup:
    """Тренер: 4 кнопки — подтвердить/отменить для девушек/парней."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('✅ Чт (девушки)', callback_data='trainer_F_yes'),
        InlineKeyboardButton('❌ Чт (девушки)', callback_data='trainer_F_no'),
    )
    kb.add(
        InlineKeyboardButton('✅ Пт (парни)', callback_data='trainer_M_yes'),
        InlineKeyboardButton('❌ Пт (парни)', callback_data='trainer_M_no'),
    )
    kb.add(InlineKeyboardButton('🏠 Главное меню', callback_data='nav_main'))
    return kb


def get_registration_keyboard(user) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления админу: пол + airsoft (все кнопки)."""
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            f'{"✅ " if user.gender == "M" else ""}👦 Парень',
            callback_data=f'reg_gender_{user.id}_M',
        ),
        InlineKeyboardButton(
            f'{"✅ " if user.gender == "F" else ""}👧 Девушка',
            callback_data=f'reg_gender_{user.id}_F',
        ),
    ).add(
        InlineKeyboardButton(
            f'{"✅ " if user.is_airsoft_member else ""}🎯 Airsoft',
            callback_data=f'reg_airsoft_{user.id}_1',
        ),
        InlineKeyboardButton(
            f'{"✅ " if not user.is_airsoft_member else ""}🚫 Не airsoft',
            callback_data=f'reg_airsoft_{user.id}_0',
        ),
    )
    return kb


def get_registration_text(user) -> str:
    """Текст уведомления админу с текущими значениями."""
    gender = {'M': '👦 Парень', 'F': '👧 Девушка'}.get(user.gender, '—')
    return (
        f'🆕 Новый пользователь\n\n'
        f'Имя: {user.display_name}\n'
        f'Username: @{user.username or "—"}\n'
        f'Telegram ID: {user.telegram_id}\n'
        f'Дата: {user.registered_at:%d.%m.%Y %H:%M}\n\n'
        f'Пол: {gender}\n'
        f'Airsoft: {"✅" if user.is_airsoft_member else "❌"}'
    )