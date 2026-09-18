from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    waiting_for_audience = State()
    waiting_for_message = State()
    confirming_broadcast = State()
