from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.database.models import CourseTariff


def get_start_registration_keyboard() -> InlineKeyboardMarkup:
    """Кнопка начала регистрации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Начать регистрацию на курс", callback_data="start_registration")]
        ]
    )


def get_cancel_registration_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены процесса регистрации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить регистрацию", callback_data="cancel_registration")]
        ]
    )


def get_tariffs_keyboard(tariffs: List[CourseTariff]) -> InlineKeyboardMarkup:
    """Список тарифов для выбора."""
    buttons = []
    for tariff in tariffs:
        formatted_price = f"{tariff.price_rub:,}".replace(",", " ")
        buttons.append([
            InlineKeyboardButton(
                text=f"{tariff.title} — {formatted_price} ₽",
                callback_data=f"view_tariff:{tariff.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tariff_detail_keyboard(tariff_id: int, price_rub: int) -> InlineKeyboardMarkup:
    """Кнопки под описанием выбранного тарифа."""
    formatted_price = f"{price_rub:,}".replace(",", " ")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить ({formatted_price} ₽)", callback_data=f"buy_tariff:{tariff_id}")],
            [InlineKeyboardButton(text="⬅️ Назад ко всем тарифам", callback_data="show_all_tariffs")]
        ]
    )


def get_course_access_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    """Кнопка перехода в закрытый канал курса после оплаты."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Войти в закрытый канал курса", url=invite_link)]
        ]
    )


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Кнопки панели администратора."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Обновить статистику", callback_data="admin_refresh_stats")],
            [InlineKeyboardButton(text="📥 Скачать базу учеников (.xlsx)", callback_data="admin_export_excel")]
        ]
    )
