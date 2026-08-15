from aiogram.fsm.state import State, StatesGroup


class PromoStates(StatesGroup):
    waiting_code = State()


class DepositStates(StatesGroup):
    waiting_amount = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirm = State()


class DirectMessageStates(StatesGroup):
    waiting_target = State()
    waiting_message = State()
    confirm = State()
