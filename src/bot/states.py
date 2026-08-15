from aiogram.fsm.state import State, StatesGroup


class PromoStates(StatesGroup):
    waiting_code = State()


class DepositStates(StatesGroup):
    waiting_amount = State()


class AdminBroadcastStates(StatesGroup):
    waiting_content = State()
    waiting_target_id = State()


class AdminManageStates(StatesGroup):
    waiting_add_id = State()
