from datetime import datetime
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from bot.config import config
from bot.database.db import get_admin_stats, get_paid_students_data
from bot.keyboards.inline import get_admin_panel_keyboard
from bot.utils.excel import create_students_excel

router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    return user_id in config.admin_id_list


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Панель администратора."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ У вас нет прав доступа к панели администратора.")
        return

    stats = await get_admin_stats()
    income_formatted = f"{stats['total_income']:,}".replace(",", " ")

    text = (
        "👑 <b>Панель администратора курсов</b>\n\n"
        "📊 <b>Текущая статистика:</b>\n"
        f"• Всего пользователей в боте: <b>{stats['total_users']}</b>\n"
        f"• Зарегистрированных (с контактами): <b>{stats['registered_users']}</b>\n"
        f"• Оплаченных покупок: <b>{stats['paid_orders']}</b>\n"
        f"• Общая сумма продаж: <b>{income_formatted} ₽</b>\n\n"
        "<i>Для выгрузки актуальной базы учеников нажмите кнопку ниже:</i>"
    )

    await message.answer(text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_refresh_stats")
async def refresh_admin_stats(callback: CallbackQuery):
    """Обновление статистики."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Статистика обновлена")
    stats = await get_admin_stats()
    income_formatted = f"{stats['total_income']:,}".replace(",", " ")

    text = (
        "👑 <b>Панель администратора курсов</b>\n\n"
        "📊 <b>Текущая статистика:</b>\n"
        f"• Всего пользователей в боте: <b>{stats['total_users']}</b>\n"
        f"• Зарегистрированных (с контактами): <b>{stats['registered_users']}</b>\n"
        f"• Оплаченных покупок: <b>{stats['paid_orders']}</b>\n"
        f"• Общая сумма продаж: <b>{income_formatted} ₽</b>\n\n"
        f"🕒 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    )

    await callback.message.edit_text(text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_export_excel")
async def export_students_to_excel(callback: CallbackQuery):
    """Выгрузка списка оплативших учеников в Excel."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Формирую файл Excel...")

    students = await get_paid_students_data()
    if not students:
        await callback.message.answer("ℹ️ В базе пока нет оплаченных заказов для выгрузки.")
        return

    excel_buffer = create_students_excel(students)
    filename = f"students_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    input_file = BufferedInputFile(
        file=excel_buffer.getvalue(),
        filename=filename
    )

    await callback.message.answer_document(
        document=input_file,
        caption=f"📄 <b>Выгрузка оплативших учеников</b>\nВсего записей: <b>{len(students)}</b>",
        parse_mode="HTML"
    )
