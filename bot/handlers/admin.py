from datetime import datetime
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from bot.config import config
from bot.database.db import (
    get_admin_stats,
    get_all_users_data,
    get_broadcast_recipients,
    get_paid_students_data,
    get_unpaid_leads_data,
)
from bot.keyboards.inline import (
    get_admin_panel_keyboard,
    get_broadcast_audience_keyboard,
    get_broadcast_confirm_keyboard,
)
from bot.states import BroadcastStates
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


# -------------------------------------------------------------
# РАССЫЛКА СООБЩЕНИЙ ПО СЕГМЕНТАМ БАЗЫ ДАННЫХ
# -------------------------------------------------------------

TARGET_TITLES = {
    "unpaid_leads": "🟡 Лиды без оплаты (оставили контакты)",
    "paid_students": "🟢 Оплатившие курс ученики",
    "all": "👥 Все пользователи бота",
}


@router.message(Command("broadcast"))
@router.callback_query(F.data == "admin_start_broadcast")
async def start_broadcast(event: Message | CallbackQuery, state: FSMContext):
    """Начало процесса рассылки сообщений."""
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("⛔️ Доступ запрещен.", show_alert=True)
        else:
            await event.answer("⛔️ У вас нет прав доступа.")
        return

    await state.clear()
    await state.set_state(BroadcastStates.waiting_for_audience)

    text = (
        "📢 <b>Массовая рассылка сообщений</b>\n\n"
        "Выберите целевую аудиторию для отправки сообщения:"
    )

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=get_broadcast_audience_keyboard(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=get_broadcast_audience_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки."""
    await state.clear()
    await callback.answer("Рассылка отменена")
    await callback.message.answer("❌ Процесс рассылки отменен.", reply_markup=get_admin_panel_keyboard())


@router.callback_query(BroadcastStates.waiting_for_audience, F.data.startswith("broadcast_target:"))
async def process_broadcast_target(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора целевой аудитории."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    target = callback.data.split(":")[1]
    recipients = await get_broadcast_recipients(target)

    if not recipients:
        await callback.answer("В этой аудитории пока нет пользователей.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(target=target, recipients=recipients)
    await state.set_state(BroadcastStates.waiting_for_message)

    target_title = TARGET_TITLES.get(target, target)
    text = (
        f"🎯 <b>Целевая аудитория:</b> {target_title}\n"
        f"👥 <b>Количество получателей:</b> {len(recipients)} чел.\n\n"
        "📝 Теперь <b>отправьте сообщение</b>, которое вы хотите разослать.\n"
        "<i>Поддерживаются текст, форматирование, ссылки, фото и видео.</i>\n\n"
        "Для отмены отправьте команду /cancel."
    )
    await callback.message.answer(text, parse_mode="HTML")


@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_content(message: Message, state: FSMContext):
    """Получение и предпросмотр сообщения перед отправкой."""
    if not is_admin(message.from_user.id):
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=get_admin_panel_keyboard())
        return

    data = await state.get_data()
    recipients = data.get("recipients", [])
    target = data.get("target", "all")
    target_title = TARGET_TITLES.get(target, target)

    # Сохраняем ID сообщения для точного копирования через bot.copy_message
    await state.update_data(
        content_chat_id=message.chat.id,
        content_message_id=message.message_id
    )
    await state.set_state(BroadcastStates.confirming_broadcast)

    # Показываем подтверждение
    await message.answer(
        f"📋 <b>Подтверждение запуска рассылки</b>\n\n"
        f"• Аудитория: <b>{target_title}</b>\n"
        f"• Получателей: <b>{len(recipients)}</b> чел.\n\n"
        f"👆 <i>Выше отображается сообщение в том виде, в котором его увидят получатели.</i>\n\n"
        "Запустить отправку?",
        reply_markup=get_broadcast_confirm_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(BroadcastStates.confirming_broadcast, F.data == "broadcast_confirm_send")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Выполнение рассылки сообщений."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Запускаю рассылку...")
    data = await state.get_data()
    recipients = data.get("recipients", [])
    from_chat_id = data.get("content_chat_id")
    msg_id = data.get("content_message_id")

    await state.clear()

    status_msg = await callback.message.answer(
        f"🚀 <b>Рассылка запущена...</b>\nВсего получателей: <b>{len(recipients)}</b>",
        parse_mode="HTML"
    )

    import asyncio
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

    sent = 0
    blocked = 0
    errors = 0

    for idx, chat_id in enumerate(recipients, 1):
        try:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=msg_id
            )
            sent += 1
            # Защита от лимитов Telegram (не более ~25 сообщений в секунду)
            await asyncio.sleep(0.04)
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=from_chat_id,
                    message_id=msg_id
                )
                sent += 1
            except Exception:
                errors += 1
        except Exception:
            errors += 1

    report_text = (
        "✅ <b>Рассылка успешно завершена!</b>\n\n"
        f"• 👥 Всего в выборке: <b>{len(recipients)}</b>\n"
        f"• 🟢 Успешно доставлено: <b>{sent}</b>\n"
        f"• 🚫 Бот заблокирован пользователем: <b>{blocked}</b>\n"
        f"• ⚠️ Ошибок отправки: <b>{errors}</b>"
    )
    await callback.message.answer(report_text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")
