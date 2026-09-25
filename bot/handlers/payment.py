import asyncio
import json
import logging
from typing import Optional
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery, SuccessfulPayment
from bot.config import config
from bot.database.models import Order, User
from bot.database.db import (
    create_order,
    get_active_tariffs,
    get_main_course_tariff,
    get_order_by_id,
    get_tariff_by_code,
    get_tariff_by_id,
    get_user_by_id,
    get_user_by_tg_id,
    mark_order_as_paid,
    update_order_provider_id,
    user_has_paid_order,
)
from bot.keyboards.inline import (
    get_autumn_tariff_keyboard,
    get_course_access_keyboard,
    get_start_registration_keyboard,
    get_tariff_detail_keyboard,
    get_tariffs_keyboard,
    get_yookassa_pay_keyboard,
)
from bot.keyboards.reply import get_main_menu_keyboard
from bot.services.yookassa import create_yookassa_payment, get_yookassa_payment

logger = logging.getLogger(__name__)
router = Router()


def get_support_payment_note() -> str:
    """Текст заботы с контактом куратора для вопросов по оплате и программе."""
    sup = config.formatted_support
    if sup:
        return (
            f"\n\n💬 <i>Возникли вопросы по оплате, счёт для юрлица или вопросы по программе? "
            f"Напишите нашему куратору {sup}, и мы с радостью поможем!</i>"
        )
    return ""


@router.message(F.text.in_({"🎓 Оплатить обучение", "🎓 Выбрать тариф и оплатить", "🍁 Оплатить обучение"}))
@router.message(Command("tariffs", "pay"))
async def show_tariffs_list(message: Message):
    """Показать экран оплаты осеннего канала без лишних промежуточных списков."""
    main_tariff = await get_main_course_tariff()
    if not main_tariff:
        await message.answer("В данный момент нет доступных для записи тарифов. Попробуйте позже.")
        return

    sup_note = get_support_payment_note()
    text = f"Стоимость осеннего канала {main_tariff.price_rub} руб , продолжительность 2 месяца   :{sup_note}"

    is_admin = message.from_user.id in config.admin_id_list
    test_tariff_id = None
    if is_admin:
        test_tariff = await get_tariff_by_code("test_1rub")
        if test_tariff:
            test_tariff_id = test_tariff.id

    keyboard = get_autumn_tariff_keyboard(
        tariff_id=main_tariff.id,
        price_rub=main_tariff.price_rub,
        is_admin=is_admin,
        test_tariff_id=test_tariff_id
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_all_tariffs")
async def callback_show_tariffs(callback: CallbackQuery):
    """Возврат к экрану оплаты по кнопке."""
    await callback.answer()
    main_tariff = await get_main_course_tariff()
    if not main_tariff:
        await callback.message.edit_text("В данный момент нет доступных для записи тарифов.")
        return

    sup_note = get_support_payment_note()
    text = f"Стоимость осеннего канала {main_tariff.price_rub} руб , продолжительность 2 месяца   :{sup_note}"

    is_admin = callback.from_user.id in config.admin_id_list
    test_tariff_id = None
    if is_admin:
        test_tariff = await get_tariff_by_code("test_1rub")
        if test_tariff:
            test_tariff_id = test_tariff.id

    keyboard = get_autumn_tariff_keyboard(
        tariff_id=main_tariff.id,
        price_rub=main_tariff.price_rub,
        is_admin=is_admin,
        test_tariff_id=test_tariff_id
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("test_pay", "test"))
async def cmd_test_pay(message: Message, bot: Bot):
    """Секретная команда для запуска тестовой оплаты на 1 рубль."""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user or not (user.phone and user.email):
        await message.answer(
            "⚠️ <b>Для проведения тестовой оплаты необходимо сначала заполнить контакты в боте!</b>\n\n"
            "Нажмите кнопку ниже для быстрой регистрации:",
            reply_markup=get_start_registration_keyboard(),
            parse_mode="HTML"
        )
        return

    test_tariff = await get_tariff_by_code("test_1rub")
    if not test_tariff:
        tariffs = await get_active_tariffs()
        test_tariff = next((t for t in tariffs if t.price_rub == 1), None)

    if not test_tariff:
        await message.answer("❌ Тестовый тариф на 1 рубль не найден в базе данных.")
        return

    await send_tariff_invoice(bot=bot, chat_id=message.chat.id, user=user, tariff=test_tariff)


@router.callback_query(F.data.startswith("view_tariff:"))
async def view_tariff_detail(callback: CallbackQuery):
    """Детальный просмотр выбранного тарифа."""
    await callback.answer()
    try:
        tariff_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        return

    tariff = await get_tariff_by_id(tariff_id)
    if not tariff:
        await callback.message.answer("Тариф не найден или более не активен.")
        return

    formatted_price = f"{tariff.price_rub:,}".replace(",", " ")
    sup_note = get_support_payment_note()

    if tariff.code == "test_1rub":
        text = (
            f"🧪 <b>{tariff.title}</b>\n\n"
            f"{tariff.description}\n\n"
            f"💰 <b>Стоимость:</b> 1 рубль"
            f"{sup_note}"
        )
    else:
        text = f"Стоимость осеннего канала {tariff.price_rub} руб , продолжительность 2 месяца   :{sup_note}"

    await callback.message.edit_text(
        text,
        reply_markup=get_tariff_detail_keyboard(tariff.id, tariff.price_rub),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("buy_tariff:") | F.data.startswith("confirm_buy_tariff:"))
async def buy_tariff(callback: CallbackQuery, bot: Bot):
    """Формирование и отправка счета на оплату через ЮKassa."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    await callback.answer()
    try:
        tariff_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        return

    user = await get_user_by_tg_id(callback.from_user.id)
    if not user or not (user.phone and user.email):
        await callback.message.answer(
            "⚠️ <b>Для оформления заказа и формирования чека необходима регистрация!</b>\n\n"
            "Пожалуйста, укажите ваши контакты (ФИО, телефон и email) перед оплатой.",
            reply_markup=get_start_registration_keyboard(),
            parse_mode="HTML"
        )
        return

    tariff = await get_tariff_by_id(tariff_id)
    if not tariff:
        await callback.message.answer("Тариф не найден.")
        return

    # Защита от случайной повторной оплаты курса
    has_paid = await user_has_paid_order(user.id)
    is_confirmed = callback.data.startswith("confirm_buy_tariff:")

    if has_paid and not is_confirmed:
        confirm_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, оплатить повторно", callback_data=f"confirm_buy_tariff:{tariff.id}")],
                [InlineKeyboardButton(text="⬅️ Отмена / Назад", callback_data="show_all_tariffs")]
            ]
        )
        await callback.message.answer(
            "⚠️ <b>Внимание: вы уже являетесь участником курса!</b>\n\n"
            f"У вас уже активирован оплаченный доступ. Вы действительно хотите оформить покупку по тарифу «{tariff.title}» повторно?",
            reply_markup=confirm_keyboard,
            parse_mode="HTML"
        )
        return

    await send_tariff_invoice(bot=bot, chat_id=callback.message.chat.id, user=user, tariff=tariff)


async def send_tariff_invoice(bot: Bot, chat_id: int, user: User, tariff):
    """
    Единая функция создания заказа и отправки инвойса:
    1. Если заданы YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY -> создает ссылку через прямой API ЮKassa.
    2. Если задан PAYMENT_PROVIDER_TOKEN -> отправляет нативный счет Telegram Payments (BotFather).
    """
    sup = config.formatted_support

    # Проверяем, настроена ли хотя бы одна платёжная система
    if not config.is_yookassa_direct and (not config.PAYMENT_PROVIDER_TOKEN or "YOUR_" in config.PAYMENT_PROVIDER_TOKEN):
        care = f" Напишите нашему куратору: {sup}" if sup else ""
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ <b>Платежная система временно настраивается администратором.</b>\n"
                f"Пожалуйста, свяжитесь с поддержкой через раздел «Помощь».{care}"
            ),
            parse_mode="HTML"
        )
        logger.warning("Ни прямой API ЮKassa, ни PAYMENT_PROVIDER_TOKEN не настроены!")
        return

    # Создаем заказ в базе данных
    order = await create_order(user_id=user.id, tariff_id=tariff.id, amount=tariff.price_rub)

    # ---------------------------------------------------------
    # ВАРИАНТ 1: Прямой официальный API ЮKassa (ShopID + SecretKey)
    # ---------------------------------------------------------
    if config.is_yookassa_direct:
        bot_info = await bot.get_me()
        bot_username = bot_info.username or "bot"
        return_url = f"https://t.me/{bot_username}"

        payment_data = await create_yookassa_payment(
            amount_rub=tariff.price_rub,
            description=f"Обучение: {tariff.title}",
            order_id=order.id,
            user_email=user.email or "client@example.com",
            user_phone=user.phone or "+79990000000",
            return_url=return_url
        )

        if not payment_data or "confirmation" not in payment_data:
            care = f" Напишите нашему куратору: {sup}" if sup else ""
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ Не удалось сформировать счет на оплату в ЮKassa.{care}\n"
                    "Пожалуйста, попробуйте позже или обратитесь в службу заботы."
                ),
                parse_mode="HTML"
            )
            return

        payment_id = payment_data.get("id")
        confirmation_url = payment_data["confirmation"].get("confirmation_url")

        # Сохраняем ID платежа ЮKassa в заказе
        await update_order_provider_id(order.id, payment_id)

        msg_text = (
            "💳 <b>Счет на оплату обучения сформирован!</b>\n\n"
            f"🍁 <b>Тариф:</b> {tariff.title}\n"
            f"💰 <b>Сумма к оплате:</b> <b>{tariff.price_rub} ₽</b>\n"
            f"👤 <b>Ученик:</b> {user.full_name} (<code>{user.email}</code>)\n\n"
            "Нажмите кнопку <b>«Оплатить на сайте ЮKassa»</b> ниже, чтобы безопасно совершить платёж.\n"
            "<i>(Доступны СБП, любые банковские карты, SberPay, T-Pay)</i>\n\n"
            "После оплаты нажмите кнопку <b>«🔄 Проверить оплату»</b> 👇"
        )

        await bot.send_message(
            chat_id=chat_id,
            text=msg_text,
            reply_markup=get_yookassa_pay_keyboard(
                pay_url=confirmation_url,
                order_id=order.id,
                price_rub=tariff.price_rub
            ),
            parse_mode="HTML"
        )

        if sup:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"💬 <i>Если при оплате возникнут сложности или нужен счёт для юрлица — "
                    f"напишите нашему куратору {sup}, и мы обязательно поможем!</i>"
                ),
                parse_mode="HTML"
            )

        # Запускаем фоновый автоматический опрос статуса в ЮKassa
        asyncio.create_task(
            poll_yookassa_payment(
                bot=bot,
                order_id=order.id,
                payment_id=payment_id,
                chat_id=chat_id,
                user_id=user.id
            )
        )
        return

    # ---------------------------------------------------------
    # ВАРИАНТ 2: Нативные Telegram Payments через BotFather
    # ---------------------------------------------------------
    clean_digits = "".join(filter(str.isdigit, user.phone or ""))
    if len(clean_digits) == 11 and clean_digits.startswith("8"):
        normalized_phone = f"+7{clean_digits[1:]}"
    elif len(clean_digits) == 11 and clean_digits.startswith("7"):
        normalized_phone = f"+{clean_digits}"
    elif user.phone and user.phone.startswith("+"):
        normalized_phone = user.phone
    else:
        normalized_phone = f"+{clean_digits}" if clean_digits else "+79990000000"

    receipt_data = {
        "receipt": {
            "items": [
                {
                    "description": f"Обучение: {tariff.title}"[:128],
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{tariff.price_rub:.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": 1
                }
            ],
            "customer": {
                "email": user.email,
                "phone": normalized_phone
            }
        }
    }

    prices = [
        LabeledPrice(
            label=f"{tariff.title}"[:32],
            amount=tariff.price_rub * 100
        )
    ]

    try:
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"Оплата: {tariff.title}"[:32],
            description=(
                f"Доступ к онлайн-курсу по тарифу «{tariff.title}». "
                f"Ученик: {user.full_name} ({user.email})."
            )[:255],
            payload=f"order:{order.id}",
            provider_token=config.PAYMENT_PROVIDER_TOKEN,
            currency="RUB",
            prices=prices,
            start_parameter=f"pay_tariff_{tariff.id}",
            provider_data=json.dumps(receipt_data)
        )
        if sup:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"💬 <i>Если при оплате картой возникнут трудности или вам удобен другой способ расчёта (перевод, СБП, счёт) — "
                    f"напишите нашему куратору {sup}, мы с радостью поможем завершить оформление вручную!</i>"
                ),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.exception("Ошибка при отправке инвойса ЮKassa: %s", e)
        care = f" Напишите нашему куратору: {sup}" if sup else ""
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"❌ Не удалось сформировать счет на оплату.{care}\n"
                "Пожалуйста, обратитесь в службу заботы."
            ),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("check_pay:"))
async def callback_check_payment(callback: CallbackQuery, bot: Bot):
    """Ручная проверка статуса оплаты по нажатию кнопки «Проверить оплату»."""
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка в номере заказа.")
        return

    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    if order.status == "paid":
        await callback.answer("✅ Этот заказ уже успешно оплачен! Доступ открыт.", show_alert=True)
        return

    if not order.provider_payment_charge_id:
        await callback.answer("Счёт ещё формируется или данные устарели.", show_alert=True)
        return

    payment_data = await get_yookassa_payment(order.provider_payment_charge_id)
    if not payment_data:
        await callback.answer("⚠️ Не удалось получить ответ от ЮKassa. Попробуйте через 10 секунд.", show_alert=True)
        return

    status = payment_data.get("status")
    if status == "succeeded":
        await callback.answer("🎉 Оплата подтверждена!")
        user = await get_user_by_id(order.user_id)
        if user:
            await grant_successful_access(
                bot=bot,
                user=user,
                order=order,
                provider_charge_id=order.provider_payment_charge_id,
                chat_id=callback.message.chat.id
            )
    elif status in ("pending", "waiting_for_capture"):
        await callback.answer(
            "⏳ Оплата ещё не поступила.\nЕсли вы только что оплатили заказ, подождите 10-15 секунд и нажмите кнопку снова.",
            show_alert=True
        )
    elif status == "canceled":
        await callback.answer(
            "❌ Платёж отменён или истёк срок действия счёта. Пожалуйста, оформите заказ заново.",
            show_alert=True
        )
    else:
        await callback.answer(f"Статус платежа: {status}. Ожидаем подтверждения от банка.", show_alert=True)


async def poll_yookassa_payment(bot: Bot, order_id: int, payment_id: str, chat_id: int, user_id: int):
    """Фоновый периодический опрос ЮKassa на случай, если ученик не нажал кнопку."""
    for _ in range(35):  # 35 проверок по 15 секунд = около 8.5 минут
        await asyncio.sleep(15)
        try:
            order = await get_order_by_id(order_id)
            if not order or order.status == "paid":
                return

            payment_data = await get_yookassa_payment(payment_id)
            if not payment_data:
                continue

            status = payment_data.get("status")
            if status == "succeeded":
                user = await get_user_by_id(user_id)
                if user:
                    await grant_successful_access(
                        bot=bot,
                        user=user,
                        order=order,
                        provider_charge_id=payment_id,
                        chat_id=chat_id
                    )
                return
            elif status == "canceled":
                logger.info("Платёж %s отменён.", payment_id)
                return
        except Exception as e:
            logger.error("Ошибка при фоновом опросе ЮKassa для заказа %s: %s", order_id, e)


async def grant_successful_access(
    bot: Bot,
    user: User,
    order: Order,
    provider_charge_id: str,
    chat_id: Optional[int] = None
):
    """Единая функция активации доступа после оплаты (и для ЮKassa API, и для BotFather)."""
    target_chat_id = chat_id or user.telegram_id

    # Отмечаем заказ в БД как оплаченный
    if order.status != "paid":
        order = await mark_order_as_paid(
            order_id=order.id,
            provider_payment_charge_id=provider_charge_id
        )

    tariff = await get_tariff_by_id(order.tariff_id) if order else None
    tariff_title = tariff.title if tariff else "Курс"

    # Генерация персональной ссылки на канал
    invite_link = config.CHANNEL_INVITE_LINK
    if config.CHANNEL_ID:
        try:
            student_label = f"Ученик {user.telegram_id}"
            if user and user.full_name:
                student_label += f" ({user.full_name[:15]})"
            link_obj = await bot.create_chat_invite_link(
                chat_id=config.CHANNEL_ID,
                name=student_label,
                member_limit=1
            )
            invite_link = link_obj.invite_link
            logger.info("Создан одноразовый инвайт для %s: %s", user.telegram_id, invite_link)
        except Exception as e:
            logger.warning(
                "Не удалось создать одноразовый инвайт в канале %s (%s). Используется статическая ссылка.",
                config.CHANNEL_ID, e
            )

    # 1. Обновляем главное меню ученика
    try:
        await bot.send_message(
            chat_id=target_chat_id,
            text="✅ <b>Оплата принята! Главное меню обновлено.</b>",
            reply_markup=get_main_menu_keyboard(is_registered=True, has_access=True),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error("Не удалось отправить обновленное меню: %s", e)

    # 2. Поздравительное сообщение с кнопкой входа в закрытый канал
    congrats_text = (
        "🎉🎉🎉 <b>ОПЛАТА УСПЕШНО ПРОШЛА!</b>\n\n"
        f"Поздравляем, <b>{user.full_name or 'Ученик'}</b>!\n"
        f"Вы успешно зачислены на курс: <b>«{tariff_title}»</b>.\n\n"
        f"💳 Сумма оплаты: <b>{order.amount} ₽</b>\n"
        f"🧾 Чек отправлен на ваш email: <code>{user.email or 'указанный при регистрации'}</code>\n\n"
        "👉 <b>Нажмите на кнопку ниже, чтобы войти в закрытый канал курса и начать обучение:</b>"
    )

    try:
        await bot.send_message(
            chat_id=target_chat_id,
            text=congrats_text,
            reply_markup=get_course_access_keyboard(invite_link),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error("Не удалось отправить поздравление ученику: %s", e)

    # 3. Уведомление администраторам с быстрой ссылкой на профиль ученика
    user_mention = f"<a href=\"tg://user?id={user.telegram_id}\">{user.full_name or 'Ученик'}</a>"
    username_str = f"@{user.username}" if user.username else "отсутствует"

    admin_notify_text = (
        "🔥 <b>НОВАЯ ОПЛАТА КУРСА!</b>\n\n"
        f"• <b>Заказ №:</b> {order.id}\n"
        f"• <b>Тариф:</b> {tariff_title}\n"
        f"• <b>Сумма:</b> {order.amount} ₽\n"
        f"• <b>Ученик:</b> {user_mention}\n"
        f"• <b>Телефон:</b> {user.phone or 'Не указан'}\n"
        f"• <b>Email:</b> {user.email or 'Не указан'}\n"
        f"• <b>Telegram:</b> {username_str} (ID: <code>{user.telegram_id}</code>)\n"
        f"• <b>ID ЮKassa:</b> <code>{provider_charge_id}</code>"
    )

    for admin_id in config.admin_id_list:
        try:
            await bot.send_message(admin_id, admin_notify_text, parse_mode="HTML")
        except Exception as e:
            logger.error("Не удалось отправить уведомление админу %s: %s", admin_id, e)


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Предварительная валидация перед проведением платежа (для BotFather Telegram Payments)."""
    payload = pre_checkout_query.invoice_payload

    if not payload.startswith("order:"):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Неверный идентификатор заказа."
        )
        return

    try:
        order_id = int(payload.split(":")[1])
        order = await get_order_by_id(order_id)

        if not order:
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Заказ не найден в системе."
            )
            return

        if order.status == "paid":
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Этот заказ уже был ранее успешно оплачен."
            )
            return

        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    except Exception as e:
        logger.exception("Ошибка при pre_checkout_query: %s", e)
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Произошла техническая ошибка при проверке заказа."
        )


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot):
    """Обработка успешной оплаты через нативные платежи Telegram Payments."""
    payment: SuccessfulPayment = message.successful_payment
    payload = payment.invoice_payload

    if not payload.startswith("order:"):
        logger.error("Получена оплата с неизвестным payload: %s", payload)
        return

    try:
        order_id = int(payload.split(":")[1])
    except (ValueError, IndexError):
        return

    order = await get_order_by_id(order_id)
    if not order:
        return

    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        return

    tg_charge_id = payment.telegram_payment_charge_id
    provider_charge_id = payment.provider_payment_charge_id or tg_charge_id

    # Вызываем единую процедуру выдачи доступа
    await grant_successful_access(
        bot=bot,
        user=user,
        order=order,
        provider_charge_id=provider_charge_id,
        chat_id=message.chat.id
    )
