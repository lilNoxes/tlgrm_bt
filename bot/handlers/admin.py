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
    find_user_by_query,
    get_user_orders_info,
    grant_manual_access,
    revoke_user_access,
    get_active_tariffs,
    get_tariff_by_id,
    user_has_paid_order,
    get_user_by_tg_id,
)
from bot.keyboards.inline import (
    get_admin_panel_keyboard,
    get_broadcast_audience_keyboard,
    get_broadcast_confirm_keyboard,
    get_cancel_search_user_keyboard,
    get_user_manage_keyboard,
    get_tariffs_for_manual_grant_keyboard,
)
from bot.states import BroadcastStates, AdminUserManageStates
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
# ПОИСК И УПРАВЛЕНИЕ ДОСТУПОМ УЧЕНИКОВ (ADMIN CRM)
# -------------------------------------------------------------


@router.message(Command("user"))
@router.callback_query(F.data == "admin_search_user")
async def start_search_user(event: Message | CallbackQuery, state: FSMContext):
    """Запрос данных для поиска ученика."""
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("⛔️ Доступ запрещен.", show_alert=True)
        else:
            await event.answer("⛔️ У вас нет прав доступа.")
        return

    await state.set_state(AdminUserManageStates.waiting_for_user_query)

    text = (
        "🔍 <b>Поиск ученика и управление доступом</b>\n\n"
        "Введите что-то одно из следующего:\n"
        "• <b>Telegram ID</b> (например, <code>123456789</code>)\n"
        "• <b>Username</b> (например, <code>@katya</code> или <code>katya</code>)\n"
        "• <b>Номер телефона</b> (например, <code>+79991234567</code>)\n"
        "• <b>ФИО или имя</b> (например, <i>Екатерина</i>)\n\n"
        "<i>Бот найдёт профиль в базе данных и позволит выдать или отозвать доступ вручную.</i>"
    )
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=get_cancel_search_user_keyboard(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=get_cancel_search_user_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_back_to_panel")
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext):
    """Возврат в панель администратора с очисткой FSM."""
    await state.clear()
    await callback.answer()
    stats = await get_admin_stats()
    text = format_stats_message(stats)
    await callback.message.edit_text(text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


async def render_user_profile_card(user) -> tuple[str, bool]:
    """Формирование карточки ученика."""
    has_paid = await user_has_paid_order(user.id)
    orders = await get_user_orders_info(user.id)

    status_str = "🟢 <b>Доступ открыт (Оплачен)</b>" if has_paid else "🟡 <b>Не оплачен (Лид)</b>"
    if not (user.phone and user.email):
        status_str = "⚪️ <b>Новый (контакты не заполнены)</b>"

    orders_text = ""
    if orders:
        orders_text = "\n📦 <b>История заказов:</b>\n"
        for o in orders[:4]:
            created_str = o["created_at"].strftime("%d.%m.%Y %H:%M") if o["created_at"] else "—"
            status_icon = "🟢" if o["status"] == "paid" else ("🔴" if o["status"] == "revoked" else "⚪️")
            orders_text += f"• {status_icon} {o['tariff_title']} — {o['amount']} ₽ ({o['status']}, {created_str})\n"
    else:
        orders_text = "\n📦 Заказов пока нет.\n"

    first_seen_str = user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "—"

    card_text = (
        f"👤 <b>Карточка ученика #{user.id}</b>\n\n"
        f"• <b>ФИО:</b> {user.full_name or '—'}\n"
        f"• <b>Username:</b> @{user.username or 'нет'}\n"
        f"• <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"• <b>Телефон:</b> {user.phone or '—'}\n"
        f"• <b>Email:</b> {user.email or '—'}\n"
        f"• <b>Первый визит:</b> {first_seen_str}\n"
        f"• <b>Текущий статус:</b> {status_str}\n"
        f"{orders_text}"
    )
    return card_text, has_paid


@router.message(AdminUserManageStates.waiting_for_user_query)
async def process_search_user_query(message: Message, state: FSMContext):
    """Обработка ввода поискового запроса."""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    query = message.text.strip()
    user = await find_user_by_query(query)

    if not user:
        await message.answer(
            "❌ <b>Пользователь не найден.</b>\n\n"
            "Проверьте корректность введённых данных (ID, @username, телефон или имя) и попробуйте ещё раз, либо нажмите отмену:",
            reply_markup=get_cancel_search_user_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.clear()
    card_text, has_paid = await render_user_profile_card(user)
    await message.answer(
        card_text,
        reply_markup=get_user_manage_keyboard(user_id=user.id, has_paid=has_paid, username=user.username),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_view_user:"))
async def view_user_by_callback(callback: CallbackQuery):
    """Просмотр карточки пользователя по ID."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])
    from bot.database.models import User
    from bot.database.db import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    await callback.answer()
    card_text, has_paid = await render_user_profile_card(user)
    await callback.message.edit_text(
        card_text,
        reply_markup=get_user_manage_keyboard(user_id=user.id, has_paid=has_paid, username=user.username),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_grant_user:"))
async def choose_tariff_for_grant(callback: CallbackQuery):
    """Выбор тарифа для ручной выдачи доступа."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])
    tariffs = await get_active_tariffs()

    if not tariffs:
        await callback.answer("В базе нет активных тарифов!", show_alert=True)
        return

    await callback.answer()
    text = (
        "🎓 <b>Ручная выдача доступа к курсу</b>\n\n"
        "Выберите тариф, по которому предоставить доступ ученику:\n"
        "<i>(Бот создаст оплаченный заказ и автоматически отправит ученику персональное поздравление со ссылкой на закрытый канал курса)</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_tariffs_for_manual_grant_keyboard(tariffs, user_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_do_grant:"))
async def execute_manual_grant(callback: CallbackQuery, bot: Bot):
    """Активация доступа и отправка уведомления ученику."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[1])
    tariff_id = int(parts[2])

    from bot.database.models import User
    from bot.database.db import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    # Фиксируем ручную оплату в БД
    order, tariff = await grant_manual_access(user_id, tariff_id, callback.from_user.id)
    await callback.answer("✅ Доступ успешно выдан!", show_alert=True)

    # Генерируем ссылку на канал
    invite_link = config.CHANNEL_INVITE_LINK
    if config.CHANNEL_ID:
        try:
            channel_chat_id = int(config.CHANNEL_ID) if config.CHANNEL_ID.lstrip("-").isdigit() else config.CHANNEL_ID
            new_link = await bot.create_chat_invite_link(
                chat_id=channel_chat_id,
                name=f"Manual: {user.full_name or user.telegram_id}",
                member_limit=1
            )
            invite_link = new_link.invite_link
        except Exception:
            pass

    # Отправляем радостное уведомление ученику в ЛС
    from bot.keyboards.inline import get_course_access_keyboard
    from bot.keyboards.reply import get_main_menu_keyboard

    student_text = (
        f"🎉 <b>Здравствуйте, {user.full_name or 'дорогой ученик'}!</b>\n\n"
        f"Администратор активировал ваш доступ к онлайн-курсу по тарифу <b>«{tariff.title}»</b>!\n\n"
        "Добро пожаловать в нашу команду! Для входа в закрытый канал и чат курса перейдите по ссылке ниже 👇"
    )
    student_notified = False
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=student_text,
            reply_markup=get_course_access_keyboard(invite_link),
            parse_mode="HTML"
        )
        # Обновляем главное меню ученика с кнопкой канала
        await bot.send_message(
            chat_id=user.telegram_id,
            text="Меню обновлено: доступ к материалам теперь открыт постоянной кнопкой ниже ⬇️",
            reply_markup=get_main_menu_keyboard(is_registered=True, has_access=True)
        )
        student_notified = True
    except Exception:
        student_notified = False

    # Возвращаем обновленную карточку администратору
    card_text, has_paid = await render_user_profile_card(user)
    notify_info = (
        "✅ <i>Ученик получил уведомление и ссылку в Telegram!</i>"
        if student_notified
        else "⚠️ <i>Не удалось доставить уведомление (возможно, бот заблокирован учеником).</i>"
    )
    result_msg = (
        f"✅ <b>Доступ успешно активирован!</b>\n"
        f"• Тариф: <b>{tariff.title}</b>\n"
        f"• Ученик: <b>{user.full_name or user.telegram_id}</b>\n"
        f"• Ссылка на канал: {invite_link}\n"
        f"{notify_info}\n\n"
        f"{card_text}"
    )

    await callback.message.edit_text(
        result_msg,
        reply_markup=get_user_manage_keyboard(user_id=user.id, has_paid=has_paid, username=user.username),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_revoke_user:"))
async def execute_manual_revoke(callback: CallbackQuery):
    """Отзыв доступа у ученика."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Доступ запрещен.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[1])
    revoked_count = await revoke_user_access(user_id)

    await callback.answer(f"Доступ отозван (отменено заказов: {revoked_count})", show_alert=True)

    from bot.database.models import User
    from bot.database.db import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()

    if user:
        card_text, has_paid = await render_user_profile_card(user)
        await callback.message.edit_text(
            f"🔴 <b>Доступ к курсу отозван администратором.</b>\n\n{card_text}",
            reply_markup=get_user_manage_keyboard(user_id=user.id, has_paid=has_paid, username=user.username),
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


async def _run_broadcast_worker(
    bot: Bot,
    admin_chat_id: int,
    status_msg_id: int,
    recipients: list[int],
    from_chat_id: int,
    msg_id: int
):
    """Фоновый воркер безопасной рассылки с мягким троттлингом и прогрессом."""
    import asyncio
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

    total = len(recipients)
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

        # Мягкий безопасный таймаут: ~14 сообщений в секунду (в 2 раза ниже официального лимита Telegram в 30/сек)
        await asyncio.sleep(0.07)

        # Обновление прогресс-бара каждые 20 сообщений
        if idx % 20 == 0 or idx == total:
            try:
                percent = int((idx / total) * 100) if total > 0 else 100
                progress_text = (
                    f"🚀 <b>Идёт рассылка сообщений...</b>\n\n"
                    f"• Прогресс: <b>{idx}</b> из <b>{total}</b> ({percent}%)\n"
                    f"• 🟢 Доставлено: <b>{sent}</b>\n"
                    f"• 🚫 Бот заблокирован: <b>{blocked}</b>"
                )
                await bot.edit_message_text(
                    text=progress_text,
                    chat_id=admin_chat_id,
                    message_id=status_msg_id,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # Итоговый отчёт для администратора
    report_text = (
        "✅ <b>Рассылка успешно завершена!</b>\n\n"
        f"• 👥 Всего получателей: <b>{total}</b>\n"
        f"• 🟢 Успешно доставлено: <b>{sent}</b>\n"
        f"• 🚫 Бот заблокирован пользователем: <b>{blocked}</b>\n"
        f"• ⚠️ Ошибок отправки: <b>{errors}</b>"
    )
    try:
        await bot.send_message(
            chat_id=admin_chat_id,
            text=report_text,
            reply_markup=get_admin_panel_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        pass


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
        f"🚀 <b>Рассылка запущена в фоновом режиме...</b>\n"
        f"Всего получателей: <b>{len(recipients)}</b>\n"
        f"<i>Скорость отправки: ~14 сообщ./сек (с защитой от Flood Control Telegram).</i>",
        parse_mode="HTML"
    )

    import asyncio
    asyncio.create_task(
        _run_broadcast_worker(
            bot=bot,
            admin_chat_id=callback.message.chat.id,
            status_msg_id=status_msg.message_id,
            recipients=recipients,
            from_chat_id=from_chat_id,
            msg_id=msg_id
        )
    )

