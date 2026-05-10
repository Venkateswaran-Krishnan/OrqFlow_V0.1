from framework.logging_config import trace_event
from framework.results import success


def login(state):
    trace_event(state, "INIT_FUNC:login")
    return success("Logged in")


def prepare_session(state):
    trace_event(state, "INIT_FUNC:prepare_session")
    return success("Session ready")


def open_case(state):
    txn = state["runtime_config"]["txn"]
    trace_event(state, f"PROCESS_FUNC:open_case:{txn['id']}", txn=txn)
    return success("Case opened")


def validate_data(state):
    trace_event(state, "PROCESS_FUNC:validate_data")
    return success("Data validated")


def submit_transaction(state):
    trace_event(state, "PROCESS_FUNC:submit_transaction")
    return success("Transaction submitted")
