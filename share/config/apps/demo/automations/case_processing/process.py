from apps.demo.shared import actions
from framework.results import success


def run_process(state):
    for step in (actions.open_case, actions.validate_data, actions.submit_transaction):
        result = step(state)
        if result["outcome"] != "SUCCESS":
            return result

    return success("Process completed")
