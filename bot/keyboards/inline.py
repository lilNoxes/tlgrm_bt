from typing import List, Optional
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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Оплатить {price_rub} руб", callback_data=f"buy_tariff:{tariff_id}")],
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


def get_cancel_email_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены на этапе ввода Email."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить регистрацию", callback_data="cancel_registration")]
        ]
    )


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Кнопки панели администратора с возможностями выгрузки, рассылки и управления учениками."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Обновить статистику", callback_data="admin_refresh_stats")],
            [InlineKeyboardButton(text="🔍 Найти ученика / Управление доступом", callback_data="admin_search_user")],
            [InlineKeyboardButton(text="📢 Сделать рассылку по базе", callback_data="admin_start_broadcast")],
            [InlineKeyboardButton(text="📥 Полный отчёт (все вкладки в 1 файле)", callback_data="admin_export_full")],
            [
                InlineKeyboardButton(text="🟢 Оплатившие", callback_data="admin_export_paid"),
                InlineKeyboardButton(text="🟡 Лиды без оплаты", callback_data="admin_export_unpaid")
            ],
            [InlineKeyboardButton(text="👥 Все пользователи бота", callback_data="admin_export_all")]
        ]
    )


def get_cancel_search_user_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены поиска пользователя."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена / Назад в меню", callback_data="admin_back_to_panel")]
        ]
    )


def get_user_manage_keyboard(user_id: int, has_paid: bool, username: Optional[str] = None) -> InlineKeyboardMarkup:
    """Кнопки действий с конкретным учеником в админке."""
    buttons = []
    # Кнопка ручной выдачи доступа
    buttons.append([InlineKeyboardButton(text="🟢 Выдать доступ вручную (Оплатил)", callback_data=f"admin_grant_user:{user_id}")])

    # Если доступ уже активен — кнопка отзыва
    if has_paid:
        buttons.append([InlineKeyboardButton(text="🔴 Отозвать доступ к курсу", callback_data=f"admin_revoke_user:{user_id}")])

    # Ссылка на личные сообщения в Telegram
    clean_username = username.lstrip("@") if username else ""
    if clean_username:
        buttons.append([InlineKeyboardButton(text="💬 Написать ученику в Telegram", url=f"https://t.me/{clean_username}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад в панель админа", callback_data="admin_back_to_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tariffs_for_manual_grant_keyboard(tariffs: List[CourseTariff], user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифа для ручной активации доступа."""
    buttons = []
    for tariff in tariffs:
        buttons.append([
            InlineKeyboardButton(
                text=f"{tariff.title} ({tariff.price_rub} ₽)",
                callback_data=f"admin_do_grant:{user_id}:{tariff.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_view_user:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_broadcast_audience_keyboard() -> InlineKeyboardMarkup:
    """Выбор целевой аудитории для рассылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟡 Только лидам без оплаты", callback_data="broadcast_target:unpaid_leads")],
            [InlineKeyboardButton(text="🟢 Только оплатившим курс", callback_data="broadcast_target:paid_students")],
            [InlineKeyboardButton(text="👥 Всем пользователям бота", callback_data="broadcast_target:all")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
        ]
    )


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Кнопки подтверждения запуска рассылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="broadcast_confirm_send")],
            [InlineKeyboardButton(text="❌ Отменить рассылку", callback_data="broadcast_cancel")]
        ]
    )

