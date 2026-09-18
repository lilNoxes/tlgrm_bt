from aiogram.fsm.state import State, StatesGroup


class AdminUserManageStates(StatesGroup):
    """Состояния FSM для поиска пользователя и ручного изменения статусов."""
    waiting_for_user_query = State()
    waiting_for_tariff_selection = State()

