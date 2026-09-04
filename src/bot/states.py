from aiogram.fsm.state import State, StatesGroup


class PromoStates(StatesGroup):
    waiting_code = State()


class DepositStates(StatesGroup):
    waiting_amount = State()


class AdminBroadcastStates(StatesGroup):
    waiting_content = State()
    waiting_target_id = State()
    confirm = State()


class AdminManageStates(StatesGroup):
    waiting_add_id = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirm = State()


class DirectMessageStates(StatesGroup):
    waiting_target = State()
    waiting_message = State()
    confirm = State()
