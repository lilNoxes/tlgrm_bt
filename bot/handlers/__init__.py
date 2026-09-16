from aiogram import Router
from .common import router as common_router
from .registration import router as registration_router
from .payment import router as payment_router
from .admin import router as admin_router


def get_main_router() -> Router:
    main_router = Router()
    main_router.include_router(admin_router)
    main_router.include_router(common_router)
    main_router.include_router(registration_router)
    main_router.include_router(payment_router)
    return main_router
