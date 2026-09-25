from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.config import config
from bot.database.db import get_or_create_user, get_user_by_tg_id, user_has_paid_order
from bot.keyboards.inline import get_course_access_keyboard, get_start_registration_keyboard
from bot.keyboards.reply import get_main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start с обязательным сбросом зависших FSM состояний."""
    await state.clear()
    telegram_id = message.from_user.id
    username = message.from_user.username
    tg_full_name = message.from_user.full_name

    user = await get_or_create_user(telegram_id=telegram_id, username=username, full_name=tg_full_name)
    has_paid = await user_has_paid_order(user.id)
    is_registered = bool(user.phone and user.email)

    welcome_text = (
        f"👋 <b>Здравствуйте, {message.from_user.first_name}!</b>\n\n"
        "Добро пожаловать в официальный бот для записи на <b>онлайн-обучение</b>!\n\n"
    )

    if has_paid:
        welcome_text += (
            "🎉 <b>Вы уже являетесь участником курса!</b>\n"
            "Все материалы и закрытый чат доступны по кнопке ниже."
        )
        await message.answer(
            welcome_text,
            reply_markup=get_main_menu_keyboard(is_registered=True, has_access=True),
            parse_mode="HTML"
        )
        await message.answer(
            "Вход в закрытый канал:",
            reply_markup=get_course_access_keyboard(config.CHANNEL_INVITE_LINK)
        )
        return

    if is_registered:
        welcome_text += (
            "✅ Вы уже заполнили контактные данные.\n"
            "Теперь вы можете перейти к оплате обучения онлайн через ЮKassa."
        )
        await message.answer(
            welcome_text,
            reply_markup=get_main_menu_keyboard(is_registered=True, has_access=False),
            parse_mode="HTML"
        )
    else:
        welcome_text += (
            "Чтобы попасть в закрытый осенний канал нужно пройти регистрацию (занимает менее 1 минуты).\n\n"
            "Нажмите кнопку <b>«Начать регистрацию»</b> ниже 👇"
        )
        await message.answer(
            welcome_text,
            reply_markup=get_main_menu_keyboard(is_registered=False, has_access=False),
            parse_mode="HTML"
        )
        await message.answer(
            "Готовы приступить к регистрации?",
            reply_markup=get_start_registration_keyboard()
        )


@router.message(F.text == "ℹ️ О курсе")
@router.message(Command("about"))
async def cmd_about(message: Message):
    """Информация о курсе."""
    text = (
        "🎓 <b>Об онлайн-курсе</b>\n\n"
        "Наш курс разработан специально для тех, кто хочет получить практические навыки и выйти на новый уровень!\n\n"
        "🔹 <b>Формат:</b> Онлайн-лекции в HD качестве, практические задания, поддержка кураторов.\n"
        "🔹 <b>Длительность:</b> от 4 до 8 недель (в зависимости от тарифа).\n"
        "🔹 <b>Результат:</b> Готовое портфолио, сертификат об окончании и доступ к закрытому комьюнити выпускников.\n\n"
        "💡 <i>Выберите тариф в главном меню, чтобы ознакомиться с подробностями каждого пакета.</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "👤 Мой профиль")
@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Просмотр личного профиля ученика."""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    has_paid = await user_has_paid_order(user.id)
    reg_status = "✅ Заполнена" if (user.phone and user.email) else "⚠️ Не завершена"
    pay_status = "🟢 Оплачен (доступ открыт)" if has_paid else "⚪️ Ожидает оплаты"

    text = (
        "👤 <b>Ваш профиль ученика</b>\n\n"
        f"• <b>ФИО:</b> {user.full_name or 'Не указано'}\n"
        f"• <b>Телефон:</b> {user.phone or 'Не указан'}\n"
        f"• <b>Email:</b> {user.email or 'Не указан'}\n"
        f"• <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"• <b>Регистрация:</b> {reg_status}\n"
        f"• <b>Статус обучения:</b> {pay_status}\n"
    )

    if not (user.phone and user.email):
        text += "\n👉 Нажмите /register или кнопку ниже, чтобы заполнить контакты."
        await message.answer(text, reply_markup=get_start_registration_keyboard(), parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


@router.message(F.text.in_({"💬 Служба заботы и поддержки", "💬 Служба заботы / Помощь"}))
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка и контакты поддержки."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    support_contact = config.SUPPORT_USERNAME.strip() if config.SUPPORT_USERNAME else ""
    clean_username = support_contact.lstrip("@")

    text = (
        "💬 <b>Служба заботы и поддержки</b>\n\n"
        "Если у вас возникли вопросы по оплате, программе курса или доступу к материалам — мы с радостью вам поможем!\n\n"
        "• Время ответа: ежедневно с 09:00 до 21:00 НСК\n"
    )

    reply_markup = None
    if clean_username:
        text += f"• Для связи напишите организаторам курса: @{clean_username}\n"
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💬 Написать организаторам", url=f"https://t.me/{clean_username}")]
            ]
        )
    else:
        text += "• Для связи напишите организаторам курса.\n"

    await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.message(F.text == "🎓 Материалы курса / Канал")
async def show_channel_access(message: Message):
    """Показать ссылку на канал для оплативших."""
    user = await get_user_by_tg_id(message.from_user.id)
    if user and await user_has_paid_order(user.id):
        await message.answer(
            "🎉 Ваш доступ к курсу активен! Перейдите в закрытый канал по ссылке:",
            reply_markup=get_course_access_keyboard(config.CHANNEL_INVITE_LINK)
        )
    else:
        await message.answer(
            "❌ У вас пока нет оплаченного доступа к материалам курса.\n"
            "Пожалуйста, выберите тариф и завершите оплату."
        )
