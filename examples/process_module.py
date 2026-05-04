from framework.logging_config import trace_event
from framework.results import success


def open_case(state, **params):
    txn = state["runtime_config"]["txn"]
    trace_event(state, f"PROCESS_FUNC:open_case:{txn['id']}", txn=txn)
    return success("Case opened")


def validate_data(state, **params):
    trace_event(state, "PROCESS_FUNC:validate_data")
    return success("Data validated")


def submit_transaction(state, **params):
    trace_event(state, "PROCESS_FUNC:submit_transaction")
    return success("Transaction submitted")
