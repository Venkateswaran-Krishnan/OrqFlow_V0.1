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
Framework startup behavior. Currently initializes the in-memory queue.

`framework/runtime/application_runtime.py`  
Application login behavior. Skips login after it has already completed for the current execution.

`framework/runtime/queue_runtime.py`  
Queue behavior: in-memory queue placeholder, fetch next transaction, wait handling, and batch count.

`framework/runtime/transition_runtime.py`  
Post-transaction decisions: success, business exception, system exception, retry, app switch, next transaction, and end.

`framework/runtime/cleanup_runtime.py`  
End behavior placeholder.

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

## Removed During Cleanup

The project was cleaned back to graph/config foundation. The following experimental areas were intentionally removed:

- `apps/`
- `examples/`
- `tests/`
- `framework/adapters.py`
- `framework/runtime_loader.py`
- `framework/steps.py`
- old `framework/services/` package
