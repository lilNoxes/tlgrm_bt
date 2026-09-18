import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import config
from bot.database.db import init_db
from bot.handlers import get_main_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot) -> None:
    """Установка списка команд в меню Telegram."""
    commands = [
        BotCommand(command="start", description="Запустить бота / Главное меню"),
        BotCommand(command="tariffs", description="Выбрать тариф и оплатить"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="help", description="Помощь и поддержка"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    """Точка входа и запуск бота."""
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error(
            "Токен бота не задан! Пожалуйста, укажите валидный BOT_TOKEN в файле .env перед запуском."
        )
        return

    # Инициализация базы данных и тарифов
    logger.info("Инициализация базы данных SQLite...")
    await init_db()
    logger.info("База данных успешно инициализирована.")

    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.exceptions import TelegramNetworkError

    # Инициализация сессии (с поддержкой прокси, если указан)
    session = None
    if config.PROXY_URL:
        logger.info("Используется прокси для подключения к Telegram: %s", config.PROXY_URL)
        session = AiohttpSession(proxy=config.PROXY_URL)

    # Инициализация бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Подключение роутеров
    dp.include_router(get_main_router())

    try:
        # Настройка команд бота
        await set_bot_commands(bot)

        logger.info("Бот запускается в режиме Polling...")
        # Не сбрасываем апдейты (drop_pending_updates=False), чтобы не потерять подтверждения оплат при перезапуске
        await bot.delete_webhook(drop_pending_updates=False)

        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramNetworkError as e:
        logger.error(
            "\n" + "=" * 72 + "\n"
            "❌ ОШИБКА ПОДКЛЮЧЕНИЯ К СЕРВЕРАМ TELEGRAM!\n\n"
            "Ваш интернет-провайдер или брандмауэр блокирует запросы к api.telegram.org:443.\n"
            "Детали: %s\n\n"
            "Решения:\n"
            "1. Включите VPN на компьютере (например, Amnezia, V2Ray, Planet VPN и т.п.)\n"
            "2. Либо настройте прокси в файле .env в строке PROXY_URL, например:\n"
            "   PROXY_URL=socks5://127.0.0.1:10808\n"
            "   или\n"
            "   PROXY_URL=http://user:password@ip:port\n"
            + "=" * 72,
            e
        )
    finally:
        await bot.session.close()
        logger.info("Сессия бота завершена.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
