import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from bot.config import config
from bot.database.models import Base, CourseTariff, Order, User

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Определяет безопасный и доступный путь для файла базы данных SQLite."""
    raw_path = config.DB_NAME.strip() if config.DB_NAME else "bot_database.db"
    db_path = Path(raw_path)

    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path

    try:
        # Пытаемся создать родительскую директорию и проверить права на запись
        db_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = db_path.parent / ".perm_check"
        test_file.touch()
        test_file.unlink()
    except (PermissionError, OSError) as e:
        logger.warning(
            "Нет доступа на запись в %s (%s). Переключаемся на домашнюю директорию.",
            db_path.parent, e
        )
        try:
            fallback_dir = Path.home() / "bot_data"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            db_path = fallback_dir / db_path.name
        except (PermissionError, OSError):
            db_path = Path("/tmp") / db_path.name

    logger.info("Используется путь к базе данных SQLite: %s", db_path)
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


DATABASE_URL = get_database_url()

from sqlalchemy import event, func, select

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Настройка WAL-режима и тайм-аута ожидания блокировок для защиты от database is locked."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Генератор асинхронной сессии для контекстного менеджера."""
    async with AsyncSessionLocal() as session:
        yield session


# Начальные тарифы курса (создаются автоматически, если таблица пуста)
DEFAULT_TARIFFS = [
    {
        "code": "test_1rub",
        "title": "🧪 Тестовый тариф",
        "description": "• Тестовый доступ для проверки приёма платежей через ЮKassa\n• Списание: ровно 1 рубль",
        "price_rub": 1,
        "is_active": True
    },
    {
        "code": "base",
        "title": "Тариф «Базовый»",
        "description": "• Доступ ко всем лекциям курса в записи\n• Домашние задания для самопроверки\n• Доступ к закрытому каналу с материалами на 3 месяца",
        "price_rub": 4900,
        "is_active": True
    },
    {
        "code": "standard",
        "title": "Тариф «С куратором» (Хит)",
        "description": "• Всё, что входит в «Базовый»\n• Проверка всех домашних заданий куратором\n• Доступ в закрытый чат участников\n• 2 групповых онлайн-разбора вопросов",
        "price_rub": 9900,
        "is_active": True
    },
    {
        "code": "vip",
        "title": "Тариф «VIP / Наставничество»",
        "description": "• Всё, что входит в «С куратором»\n• 3 личные консультации от автора курса\n• Индивидуальный план развития и доведение до результата\n• Бессрочный доступ ко всем материалам",
        "price_rub": 24900,
        "is_active": True
    }
]


async def init_db() -> None:
    """Инициализация таблиц БД и добавление базовых тарифов."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Синхронизируем тарифы: добавляем новые или обновляем существующие цены и описания
        for t_data in DEFAULT_TARIFFS:
            result = await session.execute(
                select(CourseTariff).where(CourseTariff.code == t_data["code"])
            )
            tariff = result.scalar_one_or_none()
            if tariff:
                tariff.title = t_data["title"]
                tariff.description = t_data["description"]
                tariff.price_rub = t_data["price_rub"]
                tariff.is_active = t_data.get("is_active", True)
            else:
                session.add(CourseTariff(**t_data))
        await session.commit()


async def get_or_create_user(telegram_id: int, username: Optional[str] = None, full_name: Optional[str] = None) -> User:
    """Получить или создать пользователя по его Telegram ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            # Обновим username, если изменился
            if username and user.username != username:
                user.username = username
                await session.commit()
                await session.refresh(user)
        return user


async def get_user_by_tg_id(telegram_id: int) -> Optional[User]:
    """Получить пользователя по Telegram ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


async def update_user_profile(telegram_id: int, full_name: str, phone: str, email: str) -> Optional[User]:
    """Обновить контактные данные пользователя после регистрации."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.full_name = full_name
            user.phone = phone
            user.email = email
            await session.commit()
            await session.refresh(user)
        return user


async def get_active_tariffs() -> List[CourseTariff]:
    """Получить список всех активных тарифов."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CourseTariff).where(CourseTariff.is_active == True).order_by(CourseTariff.price_rub.asc())
        )
        return list(result.scalars().all())


async def get_tariff_by_id(tariff_id: int) -> Optional[CourseTariff]:
    """Получить тариф по ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CourseTariff).where(CourseTariff.id == tariff_id))
        return result.scalar_one_or_none()


async def create_order(user_id: int, tariff_id: int, amount: int) -> Order:
    """Создать новый заказ со статусом pending."""
    async with AsyncSessionLocal() as session:
        order = Order(
            user_id=user_id,
            tariff_id=tariff_id,
            amount=amount,
            status="pending"
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def get_order_by_id(order_id: int) -> Optional[Order]:
    """Получить заказ по ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()


async def mark_order_as_paid(
    order_id: int,
    telegram_payment_charge_id: Optional[str] = None,
    provider_payment_charge_id: Optional[str] = None
) -> Optional[Order]:
    """Отметить заказ как оплаченный."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order:
            order.status = "paid"
            order.telegram_payment_charge_id = telegram_payment_charge_id
            order.provider_payment_charge_id = provider_payment_charge_id
            order.paid_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)
        return order


async def user_has_paid_order(user_id: int) -> bool:
    """Проверить, оплатил ли уже пользователь хотя бы один заказ."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(Order.user_id == user_id, Order.status == "paid")
        )
        return result.scalars().first() is not None


async def get_admin_stats() -> Dict[str, Any]:
    """Собрать расширенную статистику для администратора."""
    async with AsyncSessionLocal() as session:
        # Всего пользователей в боте
        users_count = (await session.execute(select(func.count(User.id)))).scalar_one()

        # Зарегистрированных (заполнили ФИО, телефон, email)
        registered_count = (await session.execute(
            select(func.count(User.id)).where(User.phone.isnot(None), User.email.isnot(None))
        )).scalar_one()

        # Число уникальных пользователей, оплативших хотя бы один курс
        paid_subquery = select(Order.user_id).where(Order.status == "paid").distinct()
        paid_users_count = (await session.execute(
            select(func.count(User.id)).where(User.id.in_(paid_subquery))
        )).scalar_one()

        # Лиды: оставили контакты, но ещё не оплатили
        unpaid_leads_count = max(0, registered_count - paid_users_count)

        # Новые пользователи (только зашли, ещё не заполнили контакты)
        new_users_count = max(0, users_count - registered_count)

        # Оплаченных заказов всего
        paid_orders_count = (await session.execute(
            select(func.count(Order.id)).where(Order.status == "paid")
        )).scalar_one()

        # Общая сумма оплат
        total_income = (await session.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "paid")
        )).scalar_one()

        return {
            "total_users": users_count,
            "registered_users": registered_count,
            "paid_users": paid_users_count,
            "unpaid_leads": unpaid_leads_count,
            "new_users": new_users_count,
            "paid_orders": paid_orders_count,
            "total_income": total_income,
        }


async def get_paid_students_data() -> List[Dict[str, Any]]:
    """Получить детальные данные всех оплативших студентов для Excel."""
    async with AsyncSessionLocal() as session:
        query = (
            select(Order, User, CourseTariff)
            .join(User, Order.user_id == User.id)
            .join(CourseTariff, Order.tariff_id == CourseTariff.id)
            .where(Order.status == "paid")
            .order_by(Order.paid_at.desc())
        )
        result = await session.execute(query)
        rows = result.all()

        data = []
        for order, user, tariff in rows:
            data.append({
                "order_id": order.id,
                "paid_at": order.paid_at.strftime("%Y-%m-%d %H:%M:%S") if order.paid_at else "-",
                "telegram_id": user.telegram_id,
                "username": f"@{user.username}" if user.username else "Нет",
                "full_name": user.full_name or "Не указано",
                "phone": user.phone or "Не указан",
                "email": user.email or "Не указан",
                "tariff_title": tariff.title,
                "amount_rub": order.amount,
                "provider_charge_id": order.provider_payment_charge_id or "-"
            })
        return data


async def get_unpaid_leads_data() -> List[Dict[str, Any]]:
    """Получить данные пользователей, которые заполнили контакты, но еще не оплатили курс."""
    async with AsyncSessionLocal() as session:
        paid_subquery = select(Order.user_id).where(Order.status == "paid").distinct()
        query = (
            select(User)
            .where(
                User.phone.isnot(None),
                User.email.isnot(None),
                User.id.not_in(paid_subquery)
            )
            .order_by(User.created_at.desc())
        )
        result = await session.execute(query)
        users = result.scalars().all()

        data = []
        for u in users:
            data.append({
                "telegram_id": u.telegram_id,
                "username": f"@{u.username}" if u.username else "Нет",
                "full_name": u.full_name or "Не указано",
                "phone": u.phone or "Не указан",
                "email": u.email or "Не указан",
                "registered_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "-",
            })
        return data


async def get_all_users_data() -> List[Dict[str, Any]]:
    """Получить данные всех пользователей бота (включая новых, без контактов)."""
    async with AsyncSessionLocal() as session:
        paid_subquery = select(Order.user_id).where(Order.status == "paid").distinct()
        paid_res = await session.execute(paid_subquery)
        paid_user_ids = set(paid_res.scalars().all())

        result = await session.execute(select(User).order_by(User.created_at.desc()))
        users = result.scalars().all()

        data = []
        for u in users:
            has_contacts = bool(u.phone and u.email)
            has_paid = u.id in paid_user_ids

            if has_paid:
                status_label = "🟢 Оплатил"
            elif has_contacts:
                status_label = "🟡 Зарегистрирован (без оплаты)"
            else:
                status_label = "⚪️ Новый (без контактов)"

            data.append({
                "telegram_id": u.telegram_id,
                "username": f"@{u.username}" if u.username else "Нет",
                "full_name": u.full_name or "Не заполнил",
                "phone": u.phone or "—",
                "email": u.email or "—",
                "status": status_label,
                "first_seen": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "-",
            })
        return data


async def get_broadcast_recipients(target: str) -> List[int]:
    """Получить список Telegram ID для рассылки по сегменту (all, unpaid_leads, paid_students)."""
    async with AsyncSessionLocal() as session:
        paid_subquery = select(Order.user_id).where(Order.status == "paid").distinct()

        if target == "unpaid_leads":
            # Лиды: есть контакты, но нет оплат
            query = select(User.telegram_id).where(
                User.phone.isnot(None),
                User.email.isnot(None),
                User.id.not_in(paid_subquery)
            )
        elif target == "paid_students":
            # Только оплатившие ученики
            query = select(User.telegram_id).where(User.id.in_(paid_subquery))
        else:
            # Все пользователи бота
            query = select(User.telegram_id)

        result = await session.execute(query)
        return list(result.scalars().all())
