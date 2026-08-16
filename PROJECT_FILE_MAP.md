# Project File Map

## Root Files

`bootstrap.json`  
Bootstrap input for the framework. Provides the shared root and project name used by config loading.

`pyproject.toml`  
Project/package metadata. Defines dependencies, package discovery, and the CLI entry point.

`Orqflow_Requirement.md`  
Main architecture and behavior requirement document.

`Orqflow_Requirement_Review.md`  
Review notes, open gaps, risks, and production-hardening questions.

`docs/codex-hadoff.md`  
Cross-machine project memory for decisions, cleanup notes, and current direction.

## Framework Entry

`framework/__main__.py`  
Runs when calling `python -m framework`. Forwards execution to `framework.cli.main()`.

`framework/cli.py`  
Reads the optional config/bootstrap path argument and calls `run_graph(...)`.

`framework/__init__.py`  
Package exports. Makes `build_graph` and `run_graph` importable from `framework`.

## Graph And State

`framework/graph.py`  
Builds the LangGraph workflow, configures logging, loads initial state, and invokes the graph.

`framework/nodes.py`  
Thin LangGraph node wrappers. Logs node entry and delegates runtime behavior.

`framework/state.py`  
Typed shape of the shared state dictionary passed through the graph.

## Config And Contracts

`framework/config.py`  
Loads bootstrap/project config, merges global/project/bot layers, and creates initial graph state.

`framework/results.py`  
Defines runtime outcomes and the standard result shape used by graph transitions.

`framework/logging_config.py`  
Configures logging, rotating file logs, console output, and trace events.

## Runtime

`framework/runtime/framework_lifecycle.py`  
Framework startup behavior. Loads `KeySteps.xlsx` and initializes the configured queue database adapter. Initialization failures set `SYSTEM_EXCEPTION` and route safely to `END`.

`framework/runtime/application_runtime.py`  
Application login behavior. Skips login after it has already completed for the current execution.

`framework/runtime/queue_runtime.py`  
Database-backed queue behavior: Excel/API input loading, master queue creation, transaction fetch, queue status updates, and runtime transaction assignment. Database-rejected duplicate input identifiers are recorded as informational skips; genuine insert failures remain errors.

`framework/runtime/process_runtime.py`
Selects the active application's `PROCESS_TRANSACTION` row from `KeySteps.xlsx`, imports the configured `package.module:function`, executes it, validates its result, and maps failures to framework outcomes.

`framework/runtime/transition_runtime.py`  
Post-transaction decisions: success, business exception, system exception, retry, app switch, next transaction, and end. Transition-input diagnostics use an explicit safe-field list rather than logging complete runtime state.

`framework/runtime/cleanup_runtime.py`  
Stops the browser driver, closes the queue database connection, and logs cleanup progress.

`framework/runtime/__init__.py`  
Marks the runtime package.

## Shared Runtime Assets

`share/common/__init__.py`  
Marks `share/common` as the shared utility package for process reusable code.

`share/common/exceptions.py`  
Defines shared utility exceptions, currently `CommonUtilityError`.

`share/common/excel.py`  
Reads Excel worksheets in read-only mode and returns `pandas.DataFrame` objects for process/runtime use.

`share/config/`  
Repo-local shared config model, including global config, project config, app modules, bot config, and input files.

## Tests

`tests/test_excel_master_queue.py`
Covers input loading, queue creation, SQLite/MySQL duplicate-input recognition, informational skip behavior, database status updates, transaction fetching, and genuine queue failure behavior.

`tests/test_process_runtime.py`
Covers configured process-module execution, returned results, missing application configuration, module exceptions, and exception-message logging.

`tests/test_safe_logging.py`
Covers the transaction-fetch and transition-input safe-field allowlists and verifies that customer and OCR sentinel values cannot appear in those DEBUG messages.

## Removed During Earlier Cleanup

The project was cleaned back to graph/config foundation. The following experimental areas were intentionally removed:

- `apps/`
- `examples/`
- `framework/adapters.py`
- `framework/runtime_loader.py`
- `framework/steps.py`
- old `framework/services/` package
