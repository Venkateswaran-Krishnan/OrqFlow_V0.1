from framework.results import success
from framework.logging_config import trace_event


def login(state, **params):
    trace_event(state, "INIT_FUNC:login")
    return success("Logged in")


def prepare_session(state, **params):
    trace_event(state, "INIT_FUNC:prepare_session")
    return success("Session ready")
