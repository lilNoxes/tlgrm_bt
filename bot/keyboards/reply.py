from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отправки номера телефона и кнопкой отмены."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)],
            [KeyboardButton(text="❌ Отменить регистрацию")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard


def get_main_menu_keyboard(is_registered: bool = False, has_access: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню бота."""
    buttons = []

    if has_access:
        buttons.append([KeyboardButton(text="🎓 Материалы курса / Канал")])
    else:
        buttons.append([KeyboardButton(text="🎓 Выбрать тариф и оплатить")])

    buttons.append([KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="ℹ️ О курсе")])
    buttons.append([KeyboardButton(text="💬 Служба заботы / Помощь")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Удаление клавиатуры."""
    return ReplyKeyboardRemove()
