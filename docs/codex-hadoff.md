# Codex Handoff

Date: 2026-05-08
Workspace: `C:\Users\TestBot4\Documents\Orqflow\OrqflowV0.1`

## Working Agreement

- This document is the cross-machine project memory for Codex sessions.
- Important discussions, decisions, assumptions, open questions, implementation notes, and sync status should be added here before ending a session.
- The repository is expected to be synced through the Git remote so work can continue from another PC at any time.
- Keep this handoff updated whenever architecture direction changes or source-code behavior is modified.

## 2026-05-10 Cleanup Restart Point

The project was intentionally cleaned back to the graph/config foundation so the runtime/app design can restart cleanly.

Kept:

- Graph/config/runtime foundation: `framework/graph.py`, `framework/nodes.py`, `framework/config.py`, `framework/cli.py`, `framework/state.py`, `framework/results.py`, `framework/logging_config.py`, package entrypoints, `bootstrap.json`, and `pyproject.toml`.
- Graph support services: framework lifecycle, queue runtime, transition runtime, cleanup runtime, and service package marker.
- Project memory: this handoff document.

Removed:

- Demo/application artifacts: `apps/`, `examples/`.
- Legacy CSV runner: `framework/steps.py`.
- Experimental module runtime layer: `framework/runtime_loader.py`, `framework/services/module_runtime.py`, `framework/services/execution_lifecycle.py`, `framework/services/transaction_runtime.py`, `framework/services/runtime_state.py`.
- Current tests/fixtures tied to the discarded design: `tests/`.
- Generated/runtime artifacts: `__pycache__/`, `*.pyc`, and `logs/orqflow.log`.

Follow-up code adjustments:

- `framework/nodes.py` no longer imports removed execution/transaction services.
- `execution_init` is currently a no-op graph node.
- `process_transaction` is currently a temporary success stub so graph construction remains coherent while the runtime design is rebuilt.
- `framework/services/transition_runtime.py` now owns its small transition helper functions directly.
- `framework/config.py` was simplified to load/merge config without resolving app module paths.
- `pyproject.toml` package discovery is back to `include = ["framework*"]`.

Verification:

```powershell
python -B -c "from framework.graph import build_graph; build_graph(); print('graph ok')"
```

Result:

- Graph imports and builds successfully.

## 2026-05-10 Runtime Package Cleanup

Decision:

- Remove the `framework/adapters.py` placeholder module.
- Rename the internal engine package from `framework/services` to `framework/runtime`.
- Adapters will be recreated later only if the new design needs explicit adapter boundaries.

Changes made:

- Moved kept runtime files into `framework/runtime/`.
- Updated `framework/nodes.py` imports from `framework.services.*` to `framework.runtime.*`.
- Moved the temporary `InMemoryQueue` placeholder into `framework/runtime/queue_runtime.py`.
- Removed unused placeholder concepts `BrowserDriver` and `ObjectRepository` with `framework/adapters.py`.
- Updated runtime logger namespaces from `framework.services.*` to `framework.runtime.*`.

Current kept runtime package:

```text
framework/runtime/
    __init__.py
    cleanup_runtime.py
    framework_lifecycle.py
    queue_runtime.py
    transition_runtime.py
```

Verification:

```powershell
python -B -c "from framework.graph import build_graph; build_graph(); print('graph ok')"
```

Result:

- Graph imports and builds successfully.

## 2026-05-10 Single Merged Config Object

Decision:

- The framework reads three physical config files in order:
  1. `global_config.json`
  2. `project_config.json`
  3. `<machine>/bot_config.json`
- Project config appends or overwrites global config values.
- Bot config appends or overwrites both global and project config values.
- The final merged result is the framework config object.

Change made:

- `load_initial_state(...)` now returns the merged config under `state["config"]`.
- Split top-level state keys `execution_config`, `process_config`, and `logging_config` were removed from `OrqflowState`.
- Runtime code now reads execution settings through `state["config"]["execution_config"]`.
- Graph logging setup now reads logging settings through `state["config"]["logging_config"]`.
- Effective config logging now logs one merged config object instead of separate config sections.

Current state shape:

```python
{
    "config": {...},
    "runtime_config": {...},
    "logs": [],
}
```

Verification:

```powershell
python -B -c "from framework.config import load_initial_state; s=load_initial_state(); print(sorted(s.keys())); print(sorted(s['config'].keys()))"
python -B -c "from framework.graph import build_graph; build_graph(); print('graph ok')"
```

Result:

- Initial state keys are `config`, `logs`, and `runtime_config`.
- Merged config currently contains `execution_config`, `logging_config`, and `process_config`.
- Graph imports and builds successfully.

## 2026-05-10 Machine-Specific Timestamped Logs

Decision:

- Each bot machine gets its own log folder.
- Relative `logging_config.log_file` paths are resolved from the bot machine config folder.
- When `timestamp_file` is true, the configured filename receives a run timestamp.
- The log folder is created if missing.

Example:

```text
<share_root>\config\<project>\<machine>\logs\orqflow_YYYYMMDD_HHMMSS.log
```

Current verified path:

```text
D:\share\config\orqflow_v0_1\VENKYDESKTOP\logs\orqflow_20260510_195618.log
```

Verification:

```powershell
python -m framework
python -B -c "from framework.graph import build_graph; build_graph(); print('graph ok')"
```

Result:

- Framework run completed successfully.
- Timestamped machine-specific log file was created.
- Graph imports and builds successfully.

## 2026-05-10 Master Bot Routing

Decision:

- `master_queue_creator` should run only when merged config has:

```json
{
  "process_config": {
    "settings": {
      "masterbot": true
    }
  }
}
```

Change made:

- Added `route_after_execution_init(...)` in `framework/nodes.py`.
- Replaced the fixed graph edge `execution_init -> master_queue_creator` with conditional routing in `framework/graph.py`.

Current routing:

```text
execution_init -> master_queue_creator -> get_transaction   if masterbot is true
execution_init -> get_transaction                           otherwise
```

Verification:

```powershell
python -B -c "from framework.graph import build_graph; build_graph(); print('graph ok')"
python -m framework
```

Result:

- Graph imports and builds successfully.
- With current config containing `masterbot: true`, the run logs include `NODE:MASTER_QUEUE_CREATOR`.

## Session Summary

This session was architectural analysis only until this handoff file was added.

We reviewed Python package concepts in the current repo and then focused on a design contradiction in the framework:

- The current implementation uses `framework/steps.py` as a CSV-driven generic step runner.
- The desired design is module-driven, where automation logic lives inside app-specific runtime modules such as login/init/process modules.
- Reusable logic should be shared by application, with each app owning its own shared object repository and app-specific helpers.
- `framework/services` should remain the framework's internal engine layer, not the location for business automation logic.

## 2026-05-10 Update

The first source-code refactor toward module-driven execution has been applied.

Changes made:

- Added `framework/services/module_runtime.py`.
- `framework/services/execution_lifecycle.py` now calls `run_init(state)` from the loaded init module.
- `framework/services/transaction_runtime.py` now calls `run_process(state)` from the loaded process module.
- `framework/config.py` no longer requires `automation_steps`; it only resolves that path if present for legacy compatibility.
- `framework/state.py` no longer includes `automation_steps` as part of the core runtime state shape.
- `examples/init_module.py` now defines `run_init(state)` and owns its init sequence.
- `examples/process_module.py` now defines `run_process(state)` and owns its process sequence.
- `examples/config.json` no longer points to `automation_steps.csv`.
- Added a first concrete app-grouped demo layout under `apps/demo`.
- `examples/config.json` now points to `../apps/demo/automations/case_processing/init.py` and `../apps/demo/automations/case_processing/process.py`.
- Shared demo actions now live in `apps/demo/shared/actions.py`.
- Added `apps*` to the setuptools package include list in `pyproject.toml`.

Verification:

```powershell
python -m unittest discover -s tests
```

Result:

- 1 test ran successfully.
- The demo graph marks the example transaction as `SUCCESS`.
- Logs confirm direct function execution through the module-owned init/process flows.

Current behavior after this update:

- Core execution no longer loads CSV automation steps.
- Core execution no longer calls `run_phase_steps(...)`.
- The active demo automation now lives under `apps/demo/automations/case_processing`.
- App-specific reusable demo functions now live under `apps/demo/shared`.
- `framework/steps.py` and `examples/automation_steps.csv` still exist as legacy/declarative artifacts but are no longer used by the example config or primary runtime path.

## 2026-05-10 Config Layering Update

A new `share/` folder was added to model the real shared location that will exist in production.

Config layout created:

```text
share/
    config/
        global_config.json
        orqflow_v0_1/
            project_config.json
            VENKYDESKTOP/
                bot_config.json
```

Intended config precedence:

1. `share/config/global_config.json`
2. `share/config/<project>/project_config.json`
3. `share/config/<project>/<machine_name>/bot_config.json`

Machine name resolution:

- The framework first reads `COMPUTERNAME`.
- If unavailable, it reads `HOSTNAME`.
- If unavailable, it falls back to `platform.node()`.
- The resolved machine name is used as the bot folder name under the project config folder.

Merge behavior:

- Later config layers supersede earlier layers.
- Nested dictionaries merge recursively.
- `null`, empty string, empty list, and empty object values are ignored and do not overwrite existing values.
- If the bot folder or bot config file does not exist, that layer is skipped.

Source changes for config layering:

- `framework/config.py` now supports both a single JSON config file and a project config directory.
- `load_initial_state(...)` now calls `load_config(...)` and resolves runtime paths relative to the project config directory for layered config.
- `framework/cli.py` now describes the argument as either a JSON config file or project config directory.
- `tests/test_config_loading.py` was added to verify global/project/bot layering and empty-value ignore behavior.
- `tests/test_langgraph_flow.py` now runs the graph using `share/config/orqflow_v0_1`.

Verification:

```powershell
python -m unittest discover -s tests
python -m framework share\config\orqflow_v0_1
```

Result:

- 3 tests ran successfully.
- The framework ran end-to-end from the layered share config directory.

## 2026-05-10 Sequence Logging Test

Ran the framework from the layered config path:

```powershell
python -m framework share\config\orqflow_v0_1
```

Observed execution sequence:

```text
NODE:FRAMEWORK_INIT
NODE:EXECUTION_INIT
INIT_FUNC:login
INIT_FUNC:prepare_session
NODE:MASTER_QUEUE_CREATOR
NODE:GET_TRANSACTION
NODE:PROCESS_TRANSACTION
PROCESS_FUNC:open_case:demo-1
PROCESS_FUNC:validate_data
PROCESS_FUNC:submit_transaction
NODE:TRANSITION_HUB:SUCCESS
NODE:END
```

Added an automated regression test:

- `tests/test_langgraph_flow.py::LangGraphFlowTests.test_demo_graph_logs_expected_execution_sequence`

Verification:

```powershell
python -m unittest discover -s tests
```

Result:

- 4 tests ran successfully.

## 2026-05-10 Bootstrap Config Decision

Decision:

- Use a root-level `bootstrap.json` as the first config file known to the framework.
- Do not store the shared location in `pyproject.toml`.
- `bootstrap.json` lives in the project root and points to the shared root plus project name.

Created:

```json
{
  "share_root": "share",
  "project": "orqflow_v0_1"
}
```

Runtime startup now supports:

```powershell
python -m framework
```

Default behavior:

1. Read `bootstrap.json` from the current project root.
2. Resolve `share_root` relative to the bootstrap file if it is a relative path.
3. Build the project config directory as `<share_root>/config/<project>`.
4. Merge global -> project -> machine bot config.
5. Start the graph.

Source changes:

- `framework/config.py` added `DEFAULT_BOOTSTRAP_PATH = "bootstrap.json"`.
- `load_initial_state(...)`, `load_config(...)`, and `run_graph(...)` now default to the bootstrap path.
- `framework/cli.py` now makes the config argument optional.
- `tests/test_config_loading.py` verifies bootstrap loading.
- `tests/test_langgraph_flow.py` now calls `run_graph()` with no explicit config path.

Verification:

```powershell
python -m unittest discover -s tests
python -m framework
```

Result:

- 5 tests ran successfully.
- `python -m framework` ran end-to-end using `bootstrap.json`.

## 2026-05-10 Startup Logging Fix

Issue observed:

- `logs/orqflow.log` was empty when running the framework.
- Root `bootstrap.json` had been changed to:

```json
{
  "share_root": "d://share",
  "project": "orqflow_v0_1"
}
```

Cause:

- The framework tried to load `d:\share\config\orqflow_v0_1`.
- That folder did not exist in the current environment.
- Config loading happened before logging was configured, so startup/config failures did not reach `logs/orqflow.log`.

Fix applied:

- `framework/graph.py` now configures default local logging before loading config.
- If bootstrap/shared-config loading fails, the exception is now written to `logs/orqflow.log`.
- Tests no longer depend on the real root `bootstrap.json`; they use `tests/fixtures/bootstrap.json` and `tests/fixtures/share/...`.
- `framework/config.py` bootstrap detection was hardened so it does not try to parse missing non-directory paths as JSON.

Current behavior:

- If `bootstrap.json` points to a missing shared location, `python -m framework` still fails, correctly, but the error is now logged.
- To run successfully with `share_root = "d://share"`, the shared config files must exist under `d:\share\config\orqflow_v0_1`.

Verification:

```powershell
python -m unittest discover -s tests
```

Result:

- 5 tests ran successfully.

## 2026-05-10 Shared Config Path Resolution Note

Issue observed after moving `share_root` to `D:/share`:

```text
FileNotFoundError: Runtime module not found: D:\apps\demo\automations\case_processing\init.py
```

Cause:

- `D:\share\config\orqflow_v0_1\project_config.json` contains paths such as:

```json
"init_module": "../../../apps/demo/automations/case_processing/init.py"
```

- Runtime paths are currently resolved relative to the project config directory.
- With shared config at `D:\share\config\orqflow_v0_1`, `../../../apps/...` resolves to `D:\apps\...`.
- The actual repo apps folder is under `D:\Document\PyProject\Playwright\OrqFlow_V0.1\apps`.

Design implication:

- Once config lives in a real shared location, paths to repo-owned code should not rely on fragile relative paths from the shared drive unless the shared drive intentionally mirrors the repo layout.
- Candidate solutions:
  - Use absolute paths in project config for `init_module`, `process_module`, and `object_repo_path`.
  - Add a bootstrap-level `project_root` / `code_root` and resolve app module paths relative to that.
  - Change config format to reference app/automation names, then have the framework resolve them relative to the installed project/package.

## 2026-05-10 Effective Config Logging

Request:

- After completing config loading, log all effective config keys and values.

Change made:

- `framework/graph.py` now logs the effective merged config after `load_initial_state(...)` and after configured logging is active.
- Logged sections:
  - `execution_config`
  - `process_config`
  - `logging_config`
- Values are logged as sorted, indented JSON through `framework.config`.

Example log prefix:

```text
framework.config | Effective execution_config: { ... }
framework.config | Effective process_config: { ... }
framework.config | Effective logging_config: { ... }
```

Verification:

```powershell
python -m unittest discover -s tests
```

Result:

- 5 tests ran successfully.

## 2026-05-10 Shared Config Root Convention

Decision:

- The `config` folder inside the shared location is constant.
- If `bootstrap.json` has `"share_root": "D:/share"`, the fixed config root is:

```text
D:\share\config
```

- The default shared app root is now inferred as:

```text
D:\share\config\apps
```

Config behavior:

- `app_root` remains supported as an override.
- If `process_config.app_root` is not configured, the framework uses `<share_root>\config\apps`.
- Runtime paths such as `init_module`, `process_module`, and `object_repo_path` are resolved relative to the app root.
- The app root is added to `sys.path` so app modules can import sibling app packages such as `from demo.shared import actions`.

Recommended shared config shape:

```text
D:\share
    config
        global_config.json
        apps
            demo
                automations
                    case_processing
                        init.py
                        process.py
                shared
                    actions.py
                    object_repo
        orqflow_v0_1
            project_config.json
            VENKYDESKTOP
                bot_config.json
```

Recommended `project_config.json` paths:

```json
{
  "process_config": {
    "app": "demo",
    "object_repo_path": "demo/shared/object_repo",
    "init_module": "demo/automations/case_processing/init.py",
    "process_module": "demo/automations/case_processing/process.py"
  }
}
```

Important:

- Do not use old paths like `../../../apps/demo/...` when apps live under `D:\share\config\apps`.
- Those old paths can resolve outside the intended shared config folder.

Verification:

```powershell
python -m unittest discover -s tests
```

Result:

- 6 tests ran successfully.

## 2026-05-10 App Root From Project Config

Decision refinement:

- The project folder still comes from `bootstrap.json` via the `project` key.
- The apps location should be configured inside the project config.
- The framework supports `<share_root>` as a token in config paths.

Recommended project config:

```json
{
  "process_config": {
    "app": "demo",
    "app_root": "<share_root>/config/apps",
    "object_repo_path": "demo/shared/object_repo",
    "init_module": "demo/automations/case_processing/init.py",
    "process_module": "demo/automations/case_processing/process.py"
  }
}
```

Resolution behavior:

- `<share_root>` is expanded from `bootstrap.json`.
- `app_root` is resolved first.
- `init_module`, `process_module`, and `object_repo_path` are then resolved relative to `app_root`.
- `app_root` is added to `sys.path` so app modules can import sibling shared packages, for example `from demo.shared import actions`.

Compatibility:

- If `app_root` is not configured, the framework currently falls back to `<share_root>/config/apps`.
- The preferred explicit style is to put `app_root` in `project_config.json`.

Verification:

```powershell
python -m unittest discover -s tests
```

Result:

- 7 tests ran successfully.

## Decisions Reached

### 1. `steps.py` is architecturally misaligned

Current behavior:

- `framework/steps.py` loads automation steps from CSV.
- It resolves functions dynamically from `init_module` or `process_module`.
- It runs them generically by phase.

Decision:

- This CSV-step architecture does not match the intended design.
- Automation flow should live directly in app/runtime modules, not in a generic CSV interpreter.
- `steps.py` should eventually be removed or downgraded to an optional mode, not the core execution path.

### 2. Automation ownership should be module-based

Target idea:

- `init` / `login` module owns init flow.
- `process` module owns process flow.
- Other app-defined modules can own other flows when needed.

Preferred runtime direction:

- Framework orchestrates phases and state transitions.
- App modules decide which internal functions to call and in what order.

Example target shape:

```python
result = state["init_module"].run_init(state)
result = state["process_module"].run_process(state)
```

instead of:

```python
state["automation_steps"] = load_automation_steps(...)
result = run_phase_steps(state, "init")
```

### 3. Shared code should be grouped by app

Decision:

- Reusable automation code will be grouped by application.
- Each app will have its own shared reusable code and corresponding object repository.

Recommended structure:

```text
framework/
apps/
    <app>/
        shared/
            object_repository.py
            actions.py
            navigation.py
            screenshots.py
        automations/
            <automation_name>/
                init.py
                process.py
shared/
    files.py
    excel.py
    datatables.py
```

Guideline:

- `apps/<app>/shared` = reusable code for one app
- `apps/<app>/automations` = business flows for that app
- top-level `shared` = cross-app generic helpers only

### 4. `framework/services` keeps an engine-only role

Decision:

- `framework/services` is positioned as the framework's internal implementation layer.
- It should contain orchestration/runtime mechanics only.
- It should not become the home for app-specific reusable business logic.

Examples that should remain in `framework/services`:

- execution lifecycle
- queue runtime
- transition runtime
- cleanup runtime

Examples that should not live there:

- SAP login logic
- invoice processing logic
- app selectors / object repository
- app-specific screenshot or Excel rules

## Key Technical Findings

### `framework/__init__.py`

Purpose:

- marks `framework` as a package
- exposes `build_graph` and `run_graph` at package level
- defines the intended public API via `__all__`

### `framework/__main__.py`

Purpose:

- entry point for `python -m framework`
- delegates to `framework.cli.main()`

### `framework/cli.py`

Current behavior:

- parses a required `config` argument
- calls `run_graph(args.config)`

### `framework/steps.py`

Important contradictions identified:

1. `on_error` is loaded from CSV but never used anywhere in the runtime.
2. `next_action` is only partially honored. The transition layer mostly decides next action itself, except for special cases such as `APP_SWITCH`.
3. The file implies a generic declarative step engine, but the desired architecture is code-owned flow inside runtime modules.

### `framework/services/transition_runtime.py`

Observed behavior:

- framework transition logic is driven by `Outcome`
- `next_action` is often overwritten by framework decisions such as retry, next transaction, or end

This reinforces that step-level control flow is not truly owned by the CSV schema.

## Files Inspected

- `framework/__init__.py`
- `framework/__main__.py`
- `framework/cli.py`
- `framework/config.py`
- `framework/graph.py`
- `framework/nodes.py`
- `framework/results.py`
- `framework/state.py`
- `framework/steps.py`
- `framework/services/__init__.py` directory presence only
- `framework/services/execution_lifecycle.py`
- `framework/services/runtime_state.py`
- `framework/services/transition_runtime.py`
- `framework/services/transaction_runtime.py`

Directories inspected:

- repository root
- `framework/`
- `framework/services/`
- `examples/`
- `apps/demo/`
- `share/config/`

## Commands Run

Executed in PowerShell from repo root:

```powershell
Get-Content -Path framework/__init__.py
Get-ChildItem -Path framework
Get-Content -Path framework/graph.py
Get-ChildItem -Path .
Get-ChildItem -Path framework
Get-ChildItem -Path framework/services
Get-Content -Path framework/steps.py
Get-Content -Path framework/nodes.py
Get-Content -Path framework/state.py
Get-Content -Path framework/results.py
rg -n "on_error|next_action|BUSINESS_EXCEPTION|SYSTEM_EXCEPTION|run_phase_steps|run_step" framework tests
Get-Content -Path framework/services/execution_lifecycle.py
Get-Content -Path framework/services/runtime_state.py
Get-Content -Path framework/services/transition_runtime.py
Get-Content -Path framework/__main__.py
Get-Content -Path framework/cli.py
Get-ChildItem -Path .
if (Test-Path docs) { Get-ChildItem -Path docs }
git status --short
```

Notes:

- `git status --short` failed because `git` is not available in the current shell environment.
- One attempt to read multiple service files in parallel had a malformed tool call for `transaction_runtime.py`, so that file was not opened during this session.

## File Changes Made

Created:

- `docs/codex-hadoff.md`

Added:

- `framework/services/module_runtime.py`
- `apps/__init__.py`
- `apps/demo/__init__.py`
- `apps/demo/automations/__init__.py`
- `apps/demo/automations/case_processing/__init__.py`
- `apps/demo/automations/case_processing/init.py`
- `apps/demo/automations/case_processing/process.py`
- `apps/demo/shared/__init__.py`
- `apps/demo/shared/actions.py`
- `apps/demo/shared/object_repo/.gitkeep`

Modified:

- `framework/services/execution_lifecycle.py`
- `framework/services/transaction_runtime.py`
- `framework/config.py`
- `framework/state.py`
- `examples/config.json`
- `examples/init_module.py`
- `examples/process_module.py`
- `pyproject.toml`
- `docs/codex-hadoff.md`
- `framework/cli.py`
- `tests/test_langgraph_flow.py`

Added for config layering:

- `bootstrap.json`
- `share/config/global_config.json`
- `share/config/orqflow_v0_1/project_config.json`
- `share/config/orqflow_v0_1/VENKYDESKTOP/bot_config.json`
- `tests/test_config_loading.py`
- `tests/fixtures/config/global_config.json`
- `tests/fixtures/config/demo_project/project_config.json`
- `tests/fixtures/config/demo_project/TESTBOT/bot_config.json`

## Current Project State

As of the 2026-05-10 update:

- The runtime now follows the first version of the desired module-driven architecture.
- Init flow is owned by the configured init module through `run_init(state)`.
- Process flow is owned by the configured process module through `run_process(state)`.
- The example config points to app-owned runtime modules under `apps/demo/automations/case_processing`.
- App-specific reusable code is demonstrated under `apps/demo/shared`.
- The primary tested config path is now `share/config/orqflow_v0_1`.
- Config is layered as global -> project -> machine bot config.
- The graph, transition hub, queue runtime, retry handling, and cleanup behavior remain framework-owned.
- CSV step execution remains in the repository only as legacy code pending a deletion/optional-mode decision.

## Unresolved Tasks

1. Decide whether `framework/steps.py` and `examples/automation_steps.csv` should be deleted or retained as an optional legacy/declarative mode.
2. Decide whether the first concrete package structure under `apps/demo` should become the official convention.
3. Decide where object repositories will live and how they will be loaded per app.
4. Separate app-specific reusable helpers from cross-app reusable helpers.
5. Decide whether project selection should be provided as a path, a project name, or both.
6. Decide whether bot config files should always be named `bot_config.json` or support multiple named config files inside each bot folder.
7. Add focused tests for direct init execution, direct process execution, retry behavior, app switch behavior, and queue transition behavior.

## Suggested Next Steps

1. Decide whether config should reference module file paths directly or reference app/automation names that the framework resolves.
2. Add tests around the app-grouped module layout.
3. Decide whether old `examples/init_module.py` and `examples/process_module.py` should remain as legacy examples or be removed with the CSV runner.
4. Decide how production will pass the project config path, for example `python -m framework share\config\orqflow_v0_1`.
4. Remove or isolate `framework/steps.py` after the direct-module flow is accepted.
5. Add tests for:

- direct init execution
- direct process execution
- retry behavior
- app switch behavior
- queue transition behavior

## Assumptions Captured

- The intended future architecture is app-grouped and module-driven.
- Automation logic should be authored in Python modules, not primarily in CSV.
- Reusable code is expected to be shared across automations within the same app.
- Object repositories are app-specific and should live alongside app-shared code.

## 2026-05-10 Runtime Queue Decision

- Queue initialization was moved out of `framework_init`.
- `runtime_config.first_run` now starts as `true` and means the first transaction cycle is active.
- `runtime_config.queue_initialized` now starts as `false` and prevents repeated queue setup.
- `get_transaction` initializes the current placeholder `InMemoryQueue` once, then reuses it.
- `process_transaction` marks `first_run` as `false` after the first process transaction completes.
- Logs were added for framework lifecycle startup, queue initialization/reuse, and first-run completion.
- Excel queue loading is still pending and should plug into the same `get_transaction` first-initialization point.

## 2026-05-10 Repository Share Folder

- The external `D:\share` content was copied into repo-local `share/` so config and test artifacts can sync through Git.
- Copied shared config, demo app files, bot config, and `Input01.xlsx`.
- Excluded generated files and runtime output: `__pycache__`, `*.pyc`, and machine log folders.
- `bootstrap.json` still points to `d:/share`; switching it to repo-local `share` is a separate runtime-location decision.

## 2026-05-12 Empty Queue Routing Decision

- Empty queue routing was centralized in `transition_hub`.
- `get_transaction` now routes to `process_transaction` only when a transaction is found; otherwise it routes to `transition_hub` with `last_status = NO_TRANSACTION`.
- `transition_runtime.resolve_transition(...)` now owns the wait/end decision for `NO_TRANSACTION`.
- Wait behavior reads `execution_config.wait_enabled`, `wait_limit`, and `wait_seconds`; runtime `wait_count` tracks attempts.
- When `get_transaction` later finds a transaction, it resets `runtime_config.wait_count` to `0`.
- The graph flowchart and requirements were updated so wait/end edges originate from `transition_hub`, not `get_transaction`.

## 2026-05-12 Login Application Node Decision

- Added a `login_application` node between `get_transaction` and `process_transaction`.
- When `get_transaction` finds a transaction, the graph now routes to `login_application`; empty queue still routes to `transition_hub`.
- `login_application` checks `runtime_config.application_logged_in`.
- If already logged in, it continues directly to `process_transaction`; otherwise it performs the current placeholder login, sets `application_logged_in = true`, and then continues.
- The login behavior is isolated in `framework/runtime/application_runtime.py` so real app login can be plugged in later without putting login work in the LangGraph node wrapper.

## 2026-05-12 Shared Common Excel Utility

- Created `share/common` as the shared utility home for cross-process helpers.
- Added `share/common/exceptions.py` with `CommonUtilityError`.
- Added `share/common/excel.py` with `read_excel_dataframe(path, sheet_name=None)`.
- The Excel utility uses `openpyxl.load_workbook(..., read_only=True, data_only=True)` and returns a `pandas.DataFrame`.
- The first row is treated as DataFrame headers; remaining rows become data.
- The utility raises `CommonUtilityError` for missing files, non-file paths, missing sheets, empty sheets/header rows, permission or lock failures, invalid workbook files, and unexpected read errors.
- `common.excel` logs through the standard Python logging system using logger name `common.excel`; framework/runtime code should catch utility exceptions, log stack traces at the runtime boundary, and map failures to `Outcome.SYSTEM_EXCEPTION`.
- Added project dependencies `pandas>=2.0` and `openpyxl>=3.1`.
- Decision: do not add `share_root` to `sys.path` yet. Normal package import works when the caller provides the import path, and direct `importlib` loading of `share/common/excel.py` was verified.

Verification:

```powershell
python -B -c "import sys; sys.path.insert(0, 'share'); from common.excel import read_excel_dataframe; df = read_excel_dataframe('share/config/orqflow_v0_1/Input/Input01.xlsx'); print(type(df).__name__, df.shape); print(list(df.columns))"
python -B -c "import importlib.util; spec = importlib.util.spec_from_file_location('shared_excel', 'share/common/excel.py'); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); df = module.read_excel_dataframe('share/config/orqflow_v0_1/Input/Input01.xlsx'); print(type(df).__name__, df.shape)"
python -m framework
```

Result:

- Existing workbook loaded as `DataFrame (2, 4)` with columns `TransID`, `InputDetails`, `OutputDetails`, and `Status`.
- Direct `importlib` loading also returned `DataFrame (2, 4)`.
- `python -m framework` completed successfully.
- `python -m unittest discover` found no tests in the repository.

## 2026-05-14 Framework KeySteps Loading

Decision:

- `framework_init` is now responsible for loading project-level `KeySteps.xlsx` at startup.
- The workbook lives beside `project_config.json` under the active project config directory.
- Startup state now carries resolved config location context so runtime code can locate shared utilities and project files without recalculating bootstrap paths.

Source changes:

- `framework/config.py` adds `config_context` to the initial state returned by `load_initial_state(...)`.
- `config_context` currently includes `share_root`, `project_config_dir`, and `bot_config_dir` for layered/bootstrap config.
- `framework/state.py` adds optional `config_context` and `key_steps` fields to `OrqflowState`.
- `framework/runtime/framework_lifecycle.py` loads `<share_root>/common/excel.py` through `importlib`, reads `<project_config_dir>/KeySteps.xlsx`, stores the resulting DataFrame in `state["key_steps"]`, and logs the path, shape, and columns.
- If KeySteps loading fails, initialization logs the stack trace, sets `runtime_config.last_status = Outcome.SYSTEM_EXCEPTION`, stores the error in `runtime_config.last_error`, and sets `runtime_config.next_action = "END"`.
- Added `share/config/orqflow_v0_1/KeySteps.xlsx`.

Current workbook check:

```text
share/config/orqflow_v0_1/KeySteps.xlsx
shape: (1, 7)
columns: Sequence, Bot, State, BatchCount, Application, Module, Status
```

Current state shape:

```python
{
    "config": {...},
    "config_context": {
        "share_root": "...",
        "project_config_dir": "...",
        "bot_config_dir": "...",
    },
    "runtime_config": {...},
    "key_steps": DataFrame(...),  # populated by framework_init
    "logs": [],
}
```

Verification:

```powershell
python -B -c "import importlib.util; spec=importlib.util.spec_from_file_location('shared_excel','share/common/excel.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); df=m.read_excel_dataframe('share/config/orqflow_v0_1/KeySteps.xlsx'); print(df.shape); print(list(df.columns))"
```

Result:

- `KeySteps.xlsx` loaded successfully as a DataFrame with shape `(1, 7)`.

## 2026-05-15 RPA Production Schema Baseline

- Updated `Orqflow_Requirement.md` queue section with the visible MySQL `rpa_prod` schema from the no-data dump provided on 2026-05-15.
- Captured confirmed tables: `tbl_institution`, `tbl_botlist`, `tbl_input`, `tbl_process`, `tbl_application`, and `tbl_queue`.
- Captured intended but incomplete tables from the dump command: `tbl_login`, `tbl_login_process_link`, and `tbl_output`.
- Documented the main relationships:
  - `tbl_process.Ins_ID` -> `tbl_institution.ID`
  - `tbl_input.Process` -> `tbl_process.ID`
  - `tbl_input.Processor` -> `tbl_application.ID`
  - `tbl_queue.Case_Details` -> `tbl_input.ID`
  - `tbl_queue.Application_Details` -> `tbl_application.ID`
- `tbl_input` is the main case/chargeback source table, and `tbl_queue` is the processing work-item table.
- `Input_Identifier` is unique on `tbl_input`.
- Visible queue/index signals include `Processing_Status`, `Case_ID + Process`, `Status`, and `Case_Number` lookup paths.

Open schema caveat:

- The pasted dump appears truncated or spliced around `tbl_process` and `tbl_queue`.
- The complete `CREATE TABLE` definitions for `tbl_application`, `tbl_login`, `tbl_login_process_link`, `tbl_output`, and all `tbl_queue` columns are still needed before implementing production DB SQL.

## 2026-05-15 SQLite Queue Backend Planning

- Added `docs/db_Schema_Full.sql` as the current schema baseline for SQLite queue planning.
- Added `docs/sqlite_queue_backend_plan.md`.
- SQLite is intended to manage the framework queue and replicate the production DB schema rather than introduce framework-only columns.
- `tbl_input.Case_Json` is the confirmed full input-details payload column.
- `tbl_queue.Case_Details` links queue rows to `tbl_input.ID`; it is not the JSON payload.
- Masterbot queue creation should accept supplied data as a DataFrame, regardless of whether the upstream source is Excel or an API call.
- Masterbot should insert into `tbl_input` first, then insert linked `tbl_queue` rows.
- `get_transaction` should join queue and input data, mark selected work as `In Processing`, and set `ProcessingSTART_timestamp`.
- Process runtime may update `CTO_Details`, `Evidence_Status`, `Dependency`, `Bot_Comment`, and `Output_tbl_Status`.
- `transition_hub` should write configured final success/fail/skip statuses and set `ProcessingEND_timestamp`.
- Status text should be configurable so production names can be matched exactly; `In Processing` is the confirmed in-progress value.
- Queue fetch now considers both `queue_config.in_progress_status` and `queue_config.eligible_status`, with `In Processing` prioritized first for the active application. The global eligibility check uses the same two configured statuses. Debug logging records the status priority and selected IDs without logging complete transaction payloads.

## 2026-08-03 Distinct-Application Queue Creation

Implemented master queue generation after input loading.

KeyStep contract:

- Read KeySteps from `state["key_steps"]`.
- Select rows whose trimmed, case-insensitive `State` is `PROCESS_TRANSACTION`.
- Sort by numeric `Sequence`, using workbook order for ties.
- Normalize `Application` values as positive integer `tbl_application.ID` values.
- Deduplicate normalized application IDs while preserving their first sequenced occurrence.
- Validate every distinct ID against `tbl_application` before inserting inputs or queues.
- Missing process rows, invalid application values, or nonexistent application IDs are configuration failures and route the master queue creator to `END` before writes.

Eligible input contract:

- Select all `tbl_input` rows whose `Process` matches `process_config.Process_ID`.
- Accept only null, empty, or whitespace `Status` values.
- Include both newly imported and previously existing eligible inputs.
- Process eligible inputs in ID order.

Per-input transaction:

- Insert one `tbl_queue` row for each distinct process application.
- Set `Case_Details` to the input ID, `Application_Details` to the KeyStep application ID, and `Processing_Status` to `queue_config.eligible_status` (default `Queue Created`).
- Leave `Bot_Name` empty until `get_transaction` assigns the processing bot.
- After the complete queue set succeeds, update the input to the same status and set `QueueCreation_timestamp = CURRENT_TIMESTAMP`.
- Commit the queue set and input update together.
- If any operation fails, roll back the complete set for that input, leave it eligible for retry, record the failure, and continue with later inputs.

Runtime reporting:

```python
runtime_config["queue_creation_summary"] = {
    "distinct_application_count": 2,
    "eligible_input_count": 3,
    "queued_input_count": 3,
    "created_queue_count": 6,
    "failed_input_count": 0,
    "failed_inputs": [],
}
```

Database changes:

- Added matching SQLite and MySQL named queries for application validation, eligible-input selection, queue insertion, and input status/timestamp updates.
- Existing transaction fetching and final status updates continue to use the same queue adapter boundary.

Verification:

```powershell
python -m pytest -q
python -m py_compile framework/runtime/queue_runtime.py
git diff --check
```

Result:

- `27 passed`.
- Runtime compilation and diff validation passed.

Operational note:

- The saved `KeySteps.xlsx` must contain valid numeric application IDs on its `PROCESS_TRANSACTION` rows before master queue creation can run successfully.

## 2026-08-15 Process Runtime, Routing, and Logging Update

Framework routing:

- `framework_init` now routes conditionally: successful initialization continues to `execution_init`; initialization failure with `next_action = END` routes directly to cleanup and graph end.
- A `SYSTEM_EXCEPTION` retries according to `execution_config.retry_limit`.
- When retries are exhausted and there is no active transaction, `transition_hub` routes to `END` instead of returning to `GET_TRANSACTION`.

Process-module execution:

- Added `framework/runtime/process_runtime.py`.
- `PROCESS_TRANSACTION` now selects the active application's matching KeySteps row using `queue_application_details`, `State = PROCESS_TRANSACTION`, and numeric `Sequence`.
- The KeySteps column is named `Module`.
- `Module` uses `package.module:function` format, for example `image_value_extraction.runtime:run_process`.
- The callable receives shared state and returns a mapping with `outcome` and optional `message`, `data`, and `next_action`.
- The framework validates returned outcomes and converts loading, invocation, or result-contract failures into `SYSTEM_EXCEPTION`.

Logging:

- Every graph node records an `INFO` entry event.
- Lifecycle and transition outcomes are logged at `INFO`.
- Operational values are logged at `DEBUG`; the complete effective configuration was moved from `INFO` to `DEBUG`.
- Business exceptions and rejected input rows are logged at `WARNING`.
- Technical failures are logged at `ERROR`, and unexpected raised exceptions include their message and traceback.
- Queue failure/skip reasons, row numbers, queue/input identifiers, module selection, and transition state are available at `DEBUG`.
- Document contents and extracted OCR results are intentionally not logged.

Verification:

- Added `tests/test_process_runtime.py`.
- Full test result after these updates: `31 tests passed`.
- Framework and project wheels have not yet been rebuilt or redeployed.

## 2026-08-16 Safe Logging and Duplicate-Input Handling

Safe logging:

- Transaction-fetch `DEBUG` messages use an explicit safe-field list: `queue_id`, `input_id`, and `application_id`.
- Transition-input `DEBUG` messages use an explicit safe-field list: outcome, queue ID, retry count, batch count, wait count, and requested action.
- Complete transaction dictionaries, runtime dictionaries, process results, document contents, customer data, and OCR output are not included in those messages.
- `tests/test_safe_logging.py` uses sentinel customer/OCR values and asserts that they cannot appear in captured transaction or transition messages.
- Lifecycle milestones remain at `INFO`, operational values remain at `DEBUG`, handled business failures remain at `WARNING`, and genuine technical failures remain at `ERROR` with tracebacks where appropriate.

Safe-logging deployment:

- Framework `0.1.2` was built and installed into `OrqFlow_Wheel_Test\.venv`.
- A smoke test executed against the installed package and both safe-logging regression tests passed.
- An existing log created before the safe-logging deployment was intentionally not changed or deleted.

Duplicate input handling:

- `tbl_input.Input_Identifier` continues to be enforced by the database as the idempotency key.
- SQLite unique-constraint errors and MySQL duplicate-key error `1062` are recognized as expected duplicate inputs.
- Duplicate rows are rolled back, logged at `INFO` without a traceback, counted in `input_load_summary.skipped_count`, and listed by Excel row number in `input_load_summary.skipped_rows`.
- Duplicate rows no longer increment `failed_count` or appear in `failed_rows`.
- Non-duplicate insert exceptions retain `ERROR` logging, rollback, failure summary details, and traceback behavior.
- The master queue summary now reports inserted, skipped, and failed input counts separately.

Verification:

- Added SQLite behavior coverage plus MySQL duplicate classification and non-duplicate error regression tests in `tests/test_excel_master_queue.py`.
- Full framework source suite: `35 tests passed`.

Release status:

- The duplicate-input change currently exists only in framework source.
- The already installed `framework 0.1.2` contains the safe-logging change but not the later duplicate-input change.
- Use a new `0.1.3` release before deploying the duplicate-input behavior; do not rebuild a different artifact under the existing `0.1.2` version.

## 2026-08-16 Application Batch Scheduler and Masterbot Scheduling

Scheduler behavior:

- `FRAMEWORK_INIT` validates and stores ordered `PROCESS_TRANSACTION` KeySteps definitions.
- Each process row owns its `BatchCount`: blank/zero means all eligible work; a positive integer limits finalized transactions in one application session; negative, decimal, and nonnumeric values are rejected.
- Runtime tracks the active step index, application ID, batch limit, and per-session finalized transaction count.
- Transaction fetch SQL now filters by `Application_Details`; a separate global eligibility query supports application switching and final completion decisions for both SQLite and MySQL.
- Success, skipped business exceptions, and retry-exhausted failures increment the session count. Retry attempts do not.
- Completed batches route through `EXECUTION_INIT`, reset the application session, and advance cyclically through process applications instead of ending the framework.

Execution initialization:

- Added `framework/runtime/execution_init_runtime.py` and connected the `execution_init` graph node to it.
- Supported reasons are `STARTUP`, `BATCH_COMPLETE`, `APP_SWITCH`, `RETRY`, and `MASTER_QUEUE_REFRESH`.
- Optional application-specific reset hooks come from matching `EXECUTION_INIT` KeySteps rows using `package.module:function`.
- Batch completion and application switching run the current application's reset hook, reset the session, and activate the next ordered process step.
- Retry runs the same application's reset hook, preserves the transaction/application, resets the session, and routes directly to login/process without fetching another transaction.

Masterbot scheduling:

- `masterbot: false` never runs queue creation.
- Blank/zero `master_queue_interval_hours` runs once per framework execution.
- A positive interval runs at startup and when the configured hours have elapsed; decimals are supported.
- Successful runs record a count and UTC timestamp; failed runs are not recorded as successful.
- Added `MASTER_QUEUE_WAIT`, which uses positive `execution_config.wait_seconds` polling and rejects values that could create a busy loop.

Routing and cleanup:

- An empty active application switches when another application has globally eligible work.
- When the global queue is empty, the current application session closes/resets before periodic wait or final `END` selection.
- Terminal cleanup now sets `runtime_config.next_action = "END"` after resource cleanup.
- Transition wait diagnostics no longer log the complete runtime dictionary.

Verification:

- Added execution-init, transition, scheduler-routing, and compiled-graph integration tests.
- The compiled graph processed simulated work in the expected order: `13-A`, `13-B`, `14-A`, `13-C`, `14-B`.
- Full source suite after the terminal-state fix: `74 tests passed`.
- These scheduler changes are assigned to framework release `0.1.4` and are included in the release commit.
- Source verification completed with `74 tests passed`.
- Built artifact: `dist/framework-0.1.4-py3-none-any.whl`.
- Artifact SHA-256: `7466BCAACFC92898F0F94DAC388B3BFF7018DEDE6AB6A2F76EC9AD4CCCFAC4DE`.
- The `0.1.4` wheel has not yet been installed or deployed; do not rebuild a different artifact under this version.

## 2026-08-16 No-Transaction Retry Guard

- A queue-fetch or framework system exception can occur before an active transaction is assigned.
- `TRANSITION_HUB` now checks for `txn is None` before evaluating the retry limit.
- Without an active transaction, the framework resets `retry_count` and routes directly to `END`; it does not enter login or `PROCESS_TRANSACTION`.
- System exceptions with an active transaction retain the configured retry behavior.
- Added a regression test covering the no-transaction system-exception path.
- This correction is assigned to framework release `0.1.5`.
- Full source verification: `75 tests passed`.
- Built artifact: `dist/framework-0.1.5-py3-none-any.whl`.
- Artifact SHA-256: `6D2F58E9BC73D5E76097914310DCF8DA42C5D3F1B2EC2DA7E69F6FB40D80792D`.

## 2026-08-16 Safe No-Transaction Logging

- The no-transaction queue path previously logged the complete `runtime_config` dictionary at `DEBUG`.
- That dictionary can retain process results, OCR output, customer values, and error payloads from earlier transactions.
- The message now uses an explicit safe-field list: active application ID, retry count, session batch count/limit, wait count, and master-queue run count.
- Added a sensitive-sentinel regression test proving `last_result`, OCR values, and error payloads cannot appear in this message.
- This correction is assigned to framework release `0.1.6`.
- Full source verification: `76 tests passed`.
- Built artifact: `dist/framework-0.1.6-py3-none-any.whl`.
- Artifact SHA-256: `FABCA9C14CA31154494F330D60F6616143174BC0845EBD2A6AEE5B20AC1CC3BA`.

## 2026-08-29 Final Queue Details Payload

Decision:

- Final queue updates now keep `Bot_Comment` and `CTO_Details` separate.
- `Bot_Comment` receives the human-readable process message or error reason.
- `CTO_Details` receives a JSON string from `runtime_config.cto_details`.
- Success, skipped business exceptions, and retry-exhausted failures all pass `cto_details` into final queue update.

Changes made:

- `DatabaseQueue.mark_success()` now accepts optional `reason` and `cto_details`.
- `DatabaseQueue.mark_skipped()` and `mark_failed()` now accept optional `cto_details`.
- The shared finalization path writes `CTO_Details` when a nonblank details string is provided.
- Transition runtime passes `runtime_config.last_message` on success and `runtime_config.last_error` on skipped/failed, plus `runtime_config.cto_details` on all final outcomes.
- Process runtime stores returned result data field `CTO_Details` or `cto_details` into `runtime_config.cto_details`, JSON-encoding non-string values.
- SQLite and MySQL queue finalization SQL now update `CTO_Details` independently from `Bot_Comment`.
- Package version bumped to `0.1.9`.
- Package version bumped to `0.1.10` after configurable in-progress queue prioritization, logging, and documentation updates.

Verification:

- Compile check passed with `python -m compileall framework tests`.
- Focused runtime coverage passed with `64 tests`.
- Full source suite passed with `81 tests`.
- Built artifact: `dist/framework-0.1.9-py3-none-any.whl`.
- Artifact SHA-256: `41CCD5FED4DF16DF24D132334FC7AC28D201BD60819536687015C326BD97EC7C`.
