import re
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bot.config import config
from bot.database.db import get_active_tariffs, get_or_create_user, update_user_profile
from bot.keyboards.inline import get_cancel_registration_keyboard, get_tariffs_keyboard, get_cancel_email_keyboard
from bot.keyboards.reply import get_main_menu_keyboard, get_phone_keyboard, remove_keyboard
from bot.states.registration import RegistrationStates

router = Router()

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def get_care_support_text() -> str:
    """Вежливый текст заботы с контактом администратора."""
    clean = config.SUPPORT_USERNAME.strip().lstrip("@") if config.SUPPORT_USERNAME else ""
    if clean:
        return (
            f"\n\n💬 <i>Если у вас возникли сложности или что-то не получается — не переживайте! "
            f"Вы всегда можете написать нашему куратору @{clean}, и мы поможем вам подключить доступ в ручном режиме.</i>"
        )
    return ""


@router.message(Command("cancel"))
@router.callback_query(F.data == "cancel_registration")
async def cancel_registration(event: Message | CallbackQuery, state: FSMContext):
    """Отмена регистрации."""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    care = get_care_support_text()
    text = f"❌ Регистрация отменена. Вы можете начать её в любой момент через главное меню или команду /register.{care}"

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("register"))
@router.callback_query(F.data == "start_registration")
async def start_registration(event: Message | CallbackQuery, state: FSMContext):
    """Запуск FSM цепочки регистрации."""
    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_name)

    text = (
        "📝 <b>Шаг 1 из 3: Ваше имя и фамилия</b>\n\n"
        "Пожалуйста, введите ваше имя и фамилию (так, как они будут указаны в сертификате и списке учеников):\n\n"
        "<i>Например: Екатерина Смирнова</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=get_cancel_registration_keyboard(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=get_cancel_registration_keyboard(), parse_mode="HTML")


MENU_COMMANDS_AND_BUTTONS = {
    "🎓 Выбрать тариф и оплатить",
    "ℹ️ О курсе",
    "👤 Мой профиль",
    "💬 Служба заботы / Помощь",
    "🎓 Материалы курса / Канал",
}


@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Обработка ввода ФИО."""
    if not message.text:
        await message.answer("⚠️ Пожалуйста, введите ваше имя текстом:", reply_markup=get_cancel_registration_keyboard())
        return

    text = message.text.strip()

    # Если пользователь нажал кнопку меню или отправил команду
    if text.startswith("/") or text in MENU_COMMANDS_AND_BUTTONS:
        if text == "/cancel":
            await state.clear()
            await message.answer("❌ Регистрация отменена.", reply_markup=get_main_menu_keyboard())
            return
        await message.answer(
            "⚠️ Вы находитесь на этапе регистрации.\n"
            "Пожалуйста, введите ваши настоящие имя и фамилию (например, <i>Екатерина Смирнова</i>) "
            "или нажмите /cancel для отмены.",
            reply_markup=get_cancel_registration_keyboard(),
            parse_mode="HTML"
        )
        return

    full_name = text
    if len(full_name) < 2 or len(full_name) > 100:
        care = get_care_support_text()
        await message.answer(
            f"⚠️ Пожалуйста, введите корректное имя (от 2 до 100 символов):\n\n<i>Например: Екатерина Смирнова</i>{care}",
            reply_markup=get_cancel_registration_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_for_phone)

    msg_text = (
        f"Отлично, <b>{full_name}</b>!\n\n"
        "📱 <b>Шаг 2 из 3: Номер телефона</b>\n\n"
        "Нажмите кнопку <b>«Отправить мой номер телефона»</b> ниже или введите его вручную в формате <code>+79991234567</code>:"
    )
    await message.answer(msg_text, reply_markup=get_phone_keyboard(), parse_mode="HTML")


@router.message(RegistrationStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка ввода телефона (кнопкой или текстом)."""
    # Проверка на нажатие кнопки отмены
    if message.text and message.text.strip() in {"❌ Отменить регистрацию", "/cancel"}:
        await state.clear()
        care = get_care_support_text()
        await message.answer(
            f"❌ Регистрация отменена.{care}",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    phone = None
    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = f"+{phone}"
    elif message.text:
        # Очистка и валидация телефона
        cleaned = re.sub(r"[^\d+]", "", message.text.strip())
        digits_only = re.sub(r"\D", "", cleaned)
        if len(digits_only) >= 10:
            phone = cleaned
            if not phone.startswith("+") and len(digits_only) == 11 and digits_only.startswith("7"):
                phone = f"+{digits_only}"
            elif not phone.startswith("+"):
                phone = f"+{digits_only}"

    if not phone:
        care = get_care_support_text()
        await message.answer(
            "⚠️ Не удалось распознать номер телефона.\n\n"
            "Пожалуйста, воспользуйтесь большой кнопкой <b>«📱 Отправить мой номер телефона»</b> ниже "
            f"или введите номер в международном формате (например, <code>+79991234567</code>):{care}",
            reply_markup=get_phone_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(RegistrationStates.waiting_for_email)

    text = (
        "📧 <b>Шаг 3 из 3: Адрес электронной почты</b>\n\n"
        "Email необходим для отправки официального электронного чека об оплате (согласно 54-ФЗ) "
        "и дублирования доступа к материалам курса.\n\n"
        "<i>Пожалуйста, введите ваш действующий email (например, student@mail.ru):</i>"
    )
    # Снимаем клавиатуру телефона и предлагаем инлайн-кнопку отмены
    await message.answer("...", reply_markup=remove_keyboard())
    await message.answer(text, reply_markup=get_cancel_email_keyboard(), parse_mode="HTML")


@router.message(RegistrationStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    """Обработка ввода email и завершение регистрации."""
    if not message.text:
        care = get_care_support_text()
        await message.answer(f"⚠️ Пожалуйста, введите ваш email текстом:{care}", reply_markup=get_cancel_email_keyboard(), parse_mode="HTML")
        return

    text = message.text.strip()

    if text.startswith("/") or text in MENU_COMMANDS_AND_BUTTONS or text == "❌ Отменить регистрацию":
        if text in {"/cancel", "❌ Отменить регистрацию"}:
            await state.clear()
            care = get_care_support_text()
            await message.answer(f"❌ Регистрация отменена.{care}", reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
            return
        care = get_care_support_text()
        await message.answer(
            "⚠️ Вы находитесь на этапе ввода Email.\n"
            "Пожалуйста, введите действующий адрес почты (например, <i>ivanova@gmail.com</i>) "
            f"или нажмите отмену:{care}",
            reply_markup=get_cancel_email_keyboard(),
            parse_mode="HTML"
        )
        return

    email = text

    if not EMAIL_REGEX.match(email):
        care = get_care_support_text()
        await message.answer(
            "⚠️ Введен некорректный адрес электронной почты. Проверьте формат и попробуйте снова:\n\n"
            f"<i>Например: ivanova@gmail.com</i>{care}",
            reply_markup=get_cancel_email_keyboard(),
            parse_mode="HTML"
        )
        return

    # Извлекаем все сохраненные данные
    data = await state.get_data()
    full_name = data.get("full_name")
    phone = data.get("phone")

    # Сохраняем в БД
    await update_user_profile(
        telegram_id=message.from_user.id,
        full_name=full_name,
        phone=phone,
        email=email
    )

    await state.clear()

    tariffs = await get_active_tariffs()

    success_text = (
        "🎉 <b>Поздравляем! Регистрация успешно завершена!</b>\n\n"
        f"📋 <b>Ваши данные:</b>\n"
        f"• ФИО: {full_name}\n"
        f"• Телефон: {phone}\n"
        f"• Email: {email}\n\n"
        "Теперь выберите подходящий тариф онлайн-обучения ниже, чтобы перейти к безопасной оплате через <b>ЮKassa</b> 👇"
    )

    await message.answer(success_text, reply_markup=get_main_menu_keyboard(is_registered=True), parse_mode="HTML")

    if tariffs:
        await message.answer(
            "📚 <b>Доступные тарифы курса:</b>",
            reply_markup=get_tariffs_keyboard(tariffs),
            parse_mode="HTML"
        )
