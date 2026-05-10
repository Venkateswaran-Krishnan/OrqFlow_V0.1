# Codex Handoff

Date: 2026-05-08
Workspace: `C:\Users\TestBot4\Documents\Orqflow\OrqflowV0.1`

## Session Summary

This session was architectural analysis only until this handoff file was added.

We reviewed Python package concepts in the current repo and then focused on a design contradiction in the framework:

- The current implementation uses `framework/steps.py` as a CSV-driven generic step runner.
- The desired design is module-driven, where automation logic lives inside app-specific runtime modules such as login/init/process modules.
- Reusable logic should be shared by application, with each app owning its own shared object repository and app-specific helpers.
- `framework/services` should remain the framework's internal engine layer, not the location for business automation logic.

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

No source-code behavior was changed in this session.

## Current Project State

As of this handoff:

- The repo still uses the existing CSV-step architecture.
- No refactor has been applied yet.
- The framework still initializes execution by loading automation steps from config and calling `run_phase_steps(...)`.
- The user has clarified that this is not the desired end-state architecture.

## Unresolved Tasks

1. Refactor the framework away from CSV-driven `steps.py` orchestration.
2. Define the concrete package structure for app-grouped automations and app-grouped shared code.
3. Change execution lifecycle to call module entry points such as `run_init()` and `run_process()` directly.
4. Decide whether `steps.py` will be deleted or retained as an optional legacy/declarative mode.
5. Decide where object repositories will live and how they will be loaded per app.
6. Separate app-specific reusable helpers from cross-app reusable helpers.
7. Review config format to remove or replace the current `automation_steps` dependency.

## Suggested Next Steps

1. Create a target package layout for `apps/<app>/shared` and `apps/<app>/automations`.
2. Refactor `framework/services/execution_lifecycle.py` to stop loading CSV steps for init flow.
3. Refactor `framework/services/transaction_runtime.py` to stop using phase-based generic step execution for process flow.
4. Introduce explicit module contracts such as:

```python
def run_init(state): ...
def run_process(state): ...
```

5. Update config so it points to module entry points instead of CSV step files.
6. Remove or isolate `framework/steps.py` after the direct-module flow is working.
7. Add tests for:

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

