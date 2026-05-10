from apps.demo.shared import actions
from framework.results import success


def run_init(state):
    for step in (actions.login, actions.prepare_session):
        result = step(state)
        if result["outcome"] != "SUCCESS":
            return result

    return success("Init completed")
