import json
import logging
import uuid
from typing import Any, Dict, Optional
import aiohttp
from bot.config import config

logger = logging.getLogger(__name__)

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"


async def create_yookassa_payment(
    amount_rub: int,
    description: str,
    order_id: int,
    user_email: str,
    user_phone: str,
    return_url: str = "https://t.me"
) -> Optional[Dict[str, Any]]:
    """
    Создать платеж в ЮKassa через прямой REST API v3.
    Возвращает словарь ответа ЮKassa (с id и confirmation.confirmation_url) или None при ошибке.
    """
    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы в конфигурации!")
        return None

    auth = aiohttp.BasicAuth(login=config.YOOKASSA_SHOP_ID.strip(), password=config.YOOKASSA_SECRET_KEY.strip())
    idempotence_key = str(uuid.uuid4())
    headers = {
        "Idempotence-Key": idempotence_key,
        "Content-Type": "application/json"
    }

    # Нормализация номера телефона в E.164 (+7XXXXXXXXXX)
    clean_digits = "".join(filter(str.isdigit, user_phone or ""))
    if len(clean_digits) == 11 and clean_digits.startswith("8"):
        normalized_phone = f"+7{clean_digits[1:]}"
    elif len(clean_digits) == 11 and clean_digits.startswith("7"):
        normalized_phone = f"+{clean_digits}"
    elif user_phone and user_phone.startswith("+"):
        normalized_phone = user_phone
    else:
        normalized_phone = f"+{clean_digits}" if clean_digits else "+79990000000"

    payload_with_receipt = {
        "amount": {
            "value": f"{amount_rub:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "capture": True,
        "description": description[:128],
        "metadata": {
            "order_id": str(order_id)
        },
        "receipt": {
            "customer": {
                "email": user_email,
                "phone": normalized_phone
            },
            "items": [
                {
                    "description": description[:128],
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{amount_rub:.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": 1  # 1 - без НДС
                }
            ]
        }
    }

    payload_without_receipt = {
        "amount": {
            "value": f"{amount_rub:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "capture": True,
        "description": description[:128],
        "metadata": {
            "order_id": str(order_id)
        }
    }

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Сначала пробуем создать платеж с фискальным чеком (54-ФЗ)
            async with session.post(YOOKASSA_API_URL, auth=auth, headers=headers, json=payload_with_receipt) as resp:
                resp_text = await resp.text()
                if resp.status in (200, 201):
                    data = json.loads(resp_text)
                    logger.info("Платёж ЮKassa успешно создан: id=%s (с чеком)", data.get("id"))
                    return data

                # Если ошибка связана с тем, что в магазине выключена касса ЮKassa (чек не требуется)
                logger.warning(
                    "ЮKassa вернула статус %s при попытке передать чек: %s. Пробуем запрос без чека...",
                    resp.status, resp_text
                )

            # 2. Повторяем без блока receipt (для магазинов без онлайн-кассы ЮKassa)
            headers["Idempotence-Key"] = str(uuid.uuid4())
            async with session.post(YOOKASSA_API_URL, auth=auth, headers=headers, json=payload_without_receipt) as resp2:
                resp_text2 = await resp2.text()
                if resp2.status in (200, 201):
                    data = json.loads(resp_text2)
                    logger.info("Платёж ЮKassa успешно создан: id=%s (без чека)", data.get("id"))
                    return data

                logger.error("Ошибка при создании платежа в ЮKassa: HTTP %s: %s", resp2.status, resp_text2)
                return None

    except Exception as e:
        logger.exception("Исключение при обращении к API ЮKassa: %s", e)
        return None


async def get_yookassa_payment(payment_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить текущие данные и статус платежа из ЮKassa по payment_id.
    """
    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY or not payment_id:
        return None

    url = f"{YOOKASSA_API_URL}/{payment_id}"
    auth = aiohttp.BasicAuth(login=config.YOOKASSA_SHOP_ID.strip(), password=config.YOOKASSA_SECRET_KEY.strip())

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, auth=auth) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                resp_text = await resp.text()
                logger.warning("ЮKassa GET payment %s вернул статус %s: %s", payment_id, resp.status, resp_text)
                return None
    except Exception as e:
        logger.exception("Исключение при проверке статуса платежа %s в ЮKassa: %s", payment_id, e)
        return None
