# Project File Map

## Root Files

`pyproject.toml`  
Project/package metadata. Defines dependencies and CLI entry point.

`Orqflow_Requirement.md`  
Main architecture and behavior requirement document.

`Orqflow_Requirement_Review.md`  
Review notes, open gaps, risks, and production-hardening questions.

## Framework Entry

`framework/__main__.py`  
Runs when calling `python -m framework examples\config.json`. Forwards execution to `cli.py`.

`framework/cli.py`  
Reads command-line arguments and calls `run_graph(config_path)`.

`framework/__init__.py`  
Package exports. Makes `build_graph` and `run_graph` importable from `framework`.

## Graph And State

`framework/graph.py`  
Builds the LangGraph workflow. Defines nodes, edges, and conditional routing.

`framework/nodes.py`  
Thin LangGraph node wrappers. Each node logs entry and delegates real work to a service.

`framework/state.py`  
Typed shape of the shared state dictionary passed through the graph.

## Core Runtime

`framework/config.py`  
Loads `examples/config.json`, resolves paths, and creates the initial state.

`framework/runtime_loader.py`  
Dynamically imports runtime Python files like `init_module.py` and `process_module.py`.

`framework/steps.py`  
Loads `automation_steps.csv`, filters steps by phase, calls mapped functions, and normalizes results.

`framework/results.py`  
Defines outcomes like `SUCCESS`, `BUSINESS_EXCEPTION`, `SYSTEM_EXCEPTION`, and `StepResult`.

`framework/adapters.py`  
Placeholder adapters for browser driver, object repository, and in-memory queue.

`framework/logging_config.py`  
Configures logging: level, console output, rotating file logs, and trace events.

## Services

`framework/services/framework_lifecycle.py`  
Framework startup behavior. Currently initializes the queue.

`framework/services/execution_lifecycle.py`  
Execution setup: loads init module, automation steps, repo, driver, and runs init steps.

`framework/services/queue_runtime.py`  
Queue behavior: create queue placeholder, fetch next transaction, wait handling, and batch count.

`framework/services/transaction_runtime.py`  
Transaction execution: loads process module for the current app and runs process steps.

`framework/services/transition_runtime.py`  
Post-transaction decisions: mark success/skipped/failed, retry, app switch, next transaction, and end.

`framework/services/cleanup_runtime.py`  
End behavior. Stops the driver.

`framework/services/runtime_state.py`  
Shared state helpers: store step result, clear process module, load process module, and decide next action.

## Examples

`examples/config.json`  
Demo runtime config: execution settings, logging settings, process module paths, and step file path.

`examples/automation_steps.csv`  
Step definitions. Maps phases and keywords to functions.

`examples/init_module.py`  
Demo init functions: `login` and `prepare_session`.

`examples/process_module.py`  
Demo transaction functions: `open_case`, `validate_data`, and `submit_transaction`.

## Tests

`tests/test_langgraph_flow.py`  
Basic test that runs the graph and confirms transaction success, logs, and driver cleanup.
