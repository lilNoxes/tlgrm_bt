from datetime import datetime
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from bot.config import config
from bot.database.db import (
    get_admin_stats,
    get_all_users_data,
    get_paid_students_data,
    get_unpaid_leads_data,
)
from bot.keyboards.inline import get_admin_panel_keyboard
from bot.utils.excel import (
    create_all_users_excel,
    create_full_report_excel,
    create_paid_students_excel,
    create_unpaid_leads_excel,
)

router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    return user_id in config.admin_id_list


def format_stats_message(stats: dict) -> str:
    """Форматирует красивый текст статистики для админа."""
    income_formatted = f"{stats['total_income']:,}".replace(",", " ")
    return (
        "👑 <b>Панель администратора курсов</b>\n\n"
        "📊 <b>Текущая аналитика бота:</b>\n"
        f"• Всего пользователей в боте: <b>{stats['total_users']}</b>\n"
        f"  └ ⚪️ Новые (только запустили): <b>{stats['new_users']}</b>\n"
        f"  └ 📋 Заполнили контакты (ФИО, тел, email): <b>{stats['registered_users']}</b>\n"
        f"      ├ 🟢 Оплатили курс: <b>{stats['paid_users']}</b>\n"
        f"      └ 🟡 Лиды (ждут оплаты): <b>{stats['unpaid_leads']}</b>\n\n"
        f"• Всего оплат: <b>{stats['paid_orders']}</b>\n"
        f"• Общая выручка: <b>{income_formatted} ₽</b>\n\n"
        "<i>Выберите отчёт для скачивания в формате Excel (.xlsx):</i>"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Панель администратора."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ У вас нет прав доступа к панели администратора.")
        return

    stats = await get_admin_stats()
    text = format_stats_message(stats)
    await message.answer(text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_refresh_stats")
async def refresh_admin_stats(callback: CallbackQuery):
    """Обновление статистики."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Статистика обновлена")
    stats = await get_admin_stats()
    text = format_stats_message(stats) + f"\n\n🕒 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    await callback.message.edit_text(text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_export_full")
async def export_full_report(callback: CallbackQuery):
    """Выгрузка полного сводного отчета (3 вкладки в одном файле)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Формирую полный сводный отчет...")
    paid_data = await get_paid_students_data()
    unpaid_data = await get_unpaid_leads_data()
    all_users = await get_all_users_data()

    excel_buffer = create_full_report_excel(paid_data, unpaid_data, all_users)
    filename = f"full_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    input_file = BufferedInputFile(file=excel_buffer.getvalue(), filename=filename)
    caption = (
        "📊 <b>Полный сводный отчёт (3 вкладки):</b>\n"
        f"• 🟢 Оплатившие курс: <b>{len(paid_data)}</b>\n"
        f"• 🟡 Лиды без оплаты: <b>{len(unpaid_data)}</b>\n"
        f"• 👥 Всего пользователей: <b>{len(all_users)}</b>"
    )
    await callback.message.answer_document(document=input_file, caption=caption, parse_mode="HTML")


@router.callback_query(F.data.in_({"admin_export_paid", "admin_export_excel"}))
async def export_paid_students(callback: CallbackQuery):
    """Выгрузка только оплативших учеников."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Формирую список оплативших...")
    students = await get_paid_students_data()
    if not students:
        await callback.message.answer("ℹ️ В базе пока нет оплаченных заказов.")
        return

    excel_buffer = create_paid_students_excel(students)
    filename = f"paid_students_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    input_file = BufferedInputFile(file=excel_buffer.getvalue(), filename=filename)

    await callback.message.answer_document(
        document=input_file,
        caption=f"🟢 <b>Список оплативших курс</b>\nВсего учеников: <b>{len(students)}</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_export_unpaid")
async def export_unpaid_leads(callback: CallbackQuery):
    """Выгрузка лидов: оставили контакты, но не завершили оплату."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Формирую список лидов...")
    leads = await get_unpaid_leads_data()
    if not leads:
        await callback.message.answer("ℹ️ Нет зарегистрированных пользователей без оплаты.")
        return

    excel_buffer = create_unpaid_leads_excel(leads)
    filename = f"unpaid_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    input_file = BufferedInputFile(file=excel_buffer.getvalue(), filename=filename)

    await callback.message.answer_document(
        document=input_file,
        caption=(
            f"🟡 <b>Контакты без оплаты (теплые лиды для дожима):</b>\n"
            f"Всего анкет: <b>{len(leads)}</b>\n"
            "<i>(Ученики указали ФИО, телефон и email, но пока не оплатили)</i>"
        ),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_export_all")
async def export_all_users(callback: CallbackQuery):
    """Выгрузка всех пользователей бота (включая новых)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Формирую список всех пользователей...")
    users = await get_all_users_data()
    if not users:
        await callback.message.answer("ℹ️ Пользователей в базе пока нет.")
        return

    excel_buffer = create_all_users_excel(users)
    filename = f"all_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    input_file = BufferedInputFile(file=excel_buffer.getvalue(), filename=filename)

    await callback.message.answer_document(
        document=input_file,
        caption=f"👥 <b>Все пользователи бота</b>\nВсего записей: <b>{len(users)}</b>",
        parse_mode="HTML"
    )
