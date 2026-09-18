import json
import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from bot.config import config
from bot.database.db import (
    create_order,
    get_active_tariffs,
    get_order_by_id,
    get_tariff_by_id,
    get_user_by_tg_id,
    mark_order_as_paid,
    user_has_paid_order,
)
from bot.keyboards.inline import (
    get_course_access_keyboard,
    get_start_registration_keyboard,
    get_tariff_detail_keyboard,
    get_tariffs_keyboard,
)
from bot.keyboards.reply import get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🎓 Выбрать тариф и оплатить")
@router.message(Command("tariffs"))
async def show_tariffs_list(message: Message):
    """Показать список доступных тарифов."""
    tariffs = await get_active_tariffs()
    if not tariffs:
        await message.answer("В данный момент нет доступных для записи тарифов. Попробуйте позже.")
        return

    text = (
        "📚 <b>Выберите тариф обучения:</b>\n\n"
        "Нажмите на интересующий вариант, чтобы узнать подробности и программу тарифа:"
    )
    await message.answer(text, reply_markup=get_tariffs_keyboard(tariffs), parse_mode="HTML")


@router.callback_query(F.data == "show_all_tariffs")
async def callback_show_tariffs(callback: CallbackQuery):
    """Возврат к списку тарифов по кнопке."""
    await callback.answer()
    tariffs = await get_active_tariffs()
    if not tariffs:
        await callback.message.edit_text("В данный момент нет доступных для записи тарифов.")
        return

    text = (
        "📚 <b>Выберите тариф обучения:</b>\n\n"
        "Нажмите на интересующий вариант, чтобы узнать подробности и программу тарифа:"
    )
    await callback.message.edit_text(text, reply_markup=get_tariffs_keyboard(tariffs), parse_mode="HTML")


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
    clean_sup = config.SUPPORT_USERNAME.strip().lstrip("@") if config.SUPPORT_USERNAME else ""
    sup_note = ""
    if clean_sup:
        sup_note = (
            f"\n\n💬 <i>Нужна рассрочка, счёт для юрлица или возникли вопросы по программе? "
            f"Напишите нашему куратору @{clean_sup}, и мы с радостью поможем!</i>"
        )

    text = (
        f"🎓 <b>{tariff.title}</b>\n\n"
        f"<b>Что входит в программу:</b>\n"
        f"{tariff.description or 'Подробная информация уточняется.'}\n\n"
        f"💰 <b>Стоимость:</b> {formatted_price} ₽\n\n"
        f"<i>Для перехода к безопасной оплате нажмите кнопку «Оплатить» ниже.</i>{sup_note}"
    )

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

    if not config.PAYMENT_PROVIDER_TOKEN or "YOUR_" in config.PAYMENT_PROVIDER_TOKEN:
        await callback.message.answer(
            "⚠️ <b>Платежная система временно настраивается администратором.</b>\n"
            "Пожалуйста, свяжитесь с поддержкой через раздел «Помощь».",
            parse_mode="HTML"
        )
        logger.warning("PAYMENT_PROVIDER_TOKEN is missing or not configured in .env!")
        return

    # Создаем заказ в базе данных
    order = await create_order(user_id=user.id, tariff_id=tariff.id, amount=tariff.price_rub)

    # Нормализация телефона в формат E.164 (+7XXXXXXXXXX) для чека ЮKassa
    clean_digits = "".join(filter(str.isdigit, user.phone or ""))
    if len(clean_digits) == 11 and clean_digits.startswith("8"):
        normalized_phone = f"+7{clean_digits[1:]}"
    elif len(clean_digits) == 11 and clean_digits.startswith("7"):
        normalized_phone = f"+{clean_digits}"
    elif user.phone and user.phone.startswith("+"):
        normalized_phone = user.phone
    else:
        normalized_phone = f"+{clean_digits}" if clean_digits else "+79990000000"

    # Формируем чек для 54-ФЗ (передается в ЮKassa через provider_data)
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
                    "vat_code": 1  # 1 - без НДС
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
            amount=tariff.price_rub * 100  # В копейках
        )
    ]

    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
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
        if clean_sup:
            await callback.message.answer(
                f"💬 <i>Если при оплате картой возникнут трудности или вам удобен другой способ расчёта (перевод, СБП, счёт) — "
                f"напишите нашему куратору @{clean_sup}, мы с радостью поможем завершить оформление вручную!</i>",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.exception("Ошибка при отправке инвойса ЮKassa: %s", e)
        care = f" Напишите нашему куратору: @{clean_sup}" if clean_sup else ""
        await callback.message.answer(
            f"❌ Не удалось сформировать счет на оплату.{care}\n"
            "Пожалуйста, обратитесь в службу заботы."
        )


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Предварительная валидация перед проведением платежа."""
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

        # Все проверки пройдены
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
    """Обработка успешной оплаты через ЮKassa."""
    payment: SuccessfulPayment = message.successful_payment
    payload = payment.invoice_payload

    if not payload.startswith("order:"):
        logger.error("Получена оплата с неизвестным payload: %s", payload)
        return

    order_id = int(payload.split(":")[1])
    tg_charge_id = payment.telegram_payment_charge_id
    provider_charge_id = payment.provider_payment_charge_id

    # Отмечаем заказ в БД как оплаченный
    order = await mark_order_as_paid(
        order_id=order_id,
        telegram_payment_charge_id=tg_charge_id,
        provider_payment_charge_id=provider_charge_id
    )

    user = await get_user_by_tg_id(message.from_user.id)
    tariff = await get_tariff_by_id(order.tariff_id) if order else None
    tariff_title = tariff.title if tariff else "Курс"

    # Генерация персональной ссылки на канал (если задан CHANNEL_ID и бот админ)
    invite_link = config.CHANNEL_INVITE_LINK
    if config.CHANNEL_ID:
        try:
            student_label = f"Ученик {message.from_user.id}"
            if user and user.full_name:
                student_label += f" ({user.full_name[:15]})"
            link_obj = await bot.create_chat_invite_link(
                chat_id=config.CHANNEL_ID,
                name=student_label,
                member_limit=1
            )
            invite_link = link_obj.invite_link
            logger.info("Создан одноразовый инвайт для %s: %s", message.from_user.id, invite_link)
        except Exception as e:
            logger.warning(
                "Не удалось создать одноразовый инвайт в канале %s (%s). Используется статическая ссылка.",
                config.CHANNEL_ID, e
            )

    # 1. Сначала обновляем главное меню пользователя
    await message.answer(
        "✅ <b>Оплата принята! Главное меню обновлено.</b>",
        reply_markup=get_main_menu_keyboard(is_registered=True, has_access=True),
        parse_mode="HTML"
    )

    # 2. Главное поздравительное сообщение с кнопкой перехода в канал (остается последним перед глазами)
    congrats_text = (
        "🎉🎉🎉 <b>ОПЛАТА УСПЕШНО ПРОШЛА!</b>\n\n"
        f"Поздравляем, <b>{user.full_name if user else message.from_user.first_name}</b>!\n"
        f"Вы успешно зачислены на курс по тарифу: <b>«{tariff_title}»</b>.\n\n"
        f"💳 Сумма оплаты: <b>{order.amount if order else payment.total_amount // 100} ₽</b>\n"
        f"🧾 Чек отправлен на ваш email: <code>{user.email if user else 'указанный при оплате'}</code>\n\n"
        "👉 <b>Нажмите на кнопку ниже, чтобы войти в закрытый канал курса и начать обучение:</b>"
    )

    await message.answer(
        congrats_text,
        reply_markup=get_course_access_keyboard(invite_link),
        parse_mode="HTML"
    )

    # 3. Уведомление администраторов с быстрой ссылкой на профиль ученика
    user_mention = f"<a href=\"tg://user?id={message.from_user.id}\">{user.full_name if user else message.from_user.first_name}</a>"
    username_str = f"@{message.from_user.username}" if message.from_user.username else "отсутствует"

    admin_notify_text = (
        "🔥 <b>НОВАЯ ОПЛАТА КУРСА!</b>\n\n"
        f"• <b>Заказ №:</b> {order_id}\n"
        f"• <b>Тариф:</b> {tariff_title}\n"
        f"• <b>Сумма:</b> {order.amount if order else payment.total_amount // 100} ₽\n"
        f"• <b>Ученик:</b> {user_mention}\n"
        f"• <b>Телефон:</b> {user.phone if user else 'Не указан'}\n"
        f"• <b>Email:</b> {user.email if user else 'Не указан'}\n"
        f"• <b>Telegram:</b> {username_str} (ID: <code>{message.from_user.id}</code>)\n"
        f"• <b>ID ЮKassa:</b> <code>{provider_charge_id}</code>"
    )

    for admin_id in config.admin_id_list:
        try:
            await bot.send_message(admin_id, admin_notify_text, parse_mode="HTML")
        except Exception as e:
            logger.error("Не удалось отправить уведомление админу %s: %s", admin_id, e)
