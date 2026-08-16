# Orqflow Automation Framework Requirements

## 1. Objective

Build a state-driven automation framework for RPA-style browser automation using:

- **LangGraph** for orchestration and state-machine flow control.
- **Playwright** as the browser automation execution engine.
- **Shared Config Library** for centralized configuration.
- **Shared Object Repository** for dynamic locator management.
- **DB Queue** as the transaction source, backed by the production RPA schema captured in section 9.

The framework must provide deterministic transaction processing, reusable browser execution, externalized configuration, externalized locators, and clear separation between framework lifecycle and process-specific automation logic.

## 2. Architecture Overview

The framework is organized around a shared state object that flows through LangGraph nodes.

```text
LangGraph State Orchestrator
  -> Shared State Object
  -> Nodes
       FRAMEWORK_INIT
       EXECUTION_INIT
       MASTER_QUEUE_CREATOR
       MASTER_QUEUE_WAIT
       GET_TRANSACTION
       LOGIN_APPLICATION
       PROCESS_TRANSACTION
       TRANSITION_HUB
       END
  -> Service Layer
       Framework Lifecycle Service
       Execution Init Runtime Service
       Queue Runtime Service
       Transaction Runtime Service
       Transition Runtime Service
       Cleanup Runtime Service
       Runtime State Helpers
  -> Core Components
       Browser Driver
       Object Repository
       Config Library
       Logging Config
       Queue Adapter
       Runtime Modules
       Automation Steps
```

### 2.1 Core Responsibility Split

| Component | Responsibility |
| --- | --- |
| LangGraph | Controls orchestration, routing, retry flow, transitions, and end-state decisions. |
| Nodes | Thin LangGraph-facing wrappers that log node entry and delegate node behavior to services. |
| Service Layer | Owns framework lifecycle, execution lifecycle, queue runtime, transaction runtime, transition decisions, cleanup, and runtime state helper behavior. |
| Shared State | Carries config, runtime data, driver, repository handler, and transaction context across nodes. |
| Browser Driver | Wraps Playwright engine, browser, context, and active page. |
| Object Repository | Loads and caches application/page locator definitions. |
| Config Library | Provides framework, execution, and process configuration. |
| Logging Config | Configures execution-scoped logging, log levels, console/file handlers, and rolling log files. |
| Queue Adapter | Provides transaction retrieval and status updates against the RPA queue/input tables. |
| Runtime Modules | Contains configured application reset and transaction process callables loaded at the appropriate lifecycle point. |
| Automation Steps | Excel/CSV-driven step definitions that explicitly map keywords to functions. |

### 2.2 Service Layer

The framework shall keep LangGraph node functions thin. Each node function shall log the node event and delegate behavior to a service module.

Current service responsibilities:

| Service | Responsibility |
| --- | --- |
| `framework_lifecycle` | Framework-level startup behavior such as queue adapter initialization. |
| `execution_init_runtime` | Execution-cycle coordination, optional application reset-hook execution, retry preservation, and process-step advancement. |
| `queue_runtime` | Database-backed master queue creation and scheduling, application-filtered transaction fetch, global eligibility checks, queue status updates, and transaction assignment. |
| `process_runtime` | Ordered KeySteps scheduler setup, per-session batch tracking, process-module selection, dynamic callable loading, result validation, and process execution. |
| `transition_runtime` | Final transaction status updates and batch, retry, application-switch, wait, and end decisions. |
| `cleanup_runtime` | Driver/database shutdown, final runtime action assignment, and execution cleanup. |

## 3. State Management

### 3.1 Principle

The system shall maintain a single shared state object passed across all LangGraph nodes. The state is the single source of truth for orchestration, runtime decisions, current transaction context, driver access, repository access, and process execution state.

### 3.2 State Sections

```text
state
  config
    execution_config
    process_config
    logging_config
    queue_config
    queue_database
  config_context
  runtime_config
    retry_count
    batch_count
    active_process_step_index
    active_application_id
    active_batch_limit
    session_batch_count
    execution_init_reason
    master_queue_run_count
    master_queue_last_run_at
    wait_count
    txn
    last_status
    last_error
    next_action
  key_steps
  process_steps
  queue_db
  queue
  repo
  driver
  logs
```

### 3.3 Mutability Rules

| State Section | Mutability | Rule |
| --- | --- | --- |
| `config` | Read-only | Merged global, project, and bot configuration; contains execution, process, logging, queue, and database sections. |
| `config_context` | Read-only | Resolved bootstrap/shared/project/bot paths used by runtime loaders. |
| `runtime_config` | Mutable | Updated by services to track retries, batch counts, wait counts, transaction context, errors, and routing actions. |
| `key_steps` | Read-only runtime data | `KeySteps.xlsx` DataFrame loaded once during framework initialization. |
| `process_steps` | Mutable scheduler data | Ordered and validated `PROCESS_TRANSACTION` definitions used for application-session scheduling. |
| `queue_db` | Mutable runtime component | Active SQLite or MySQL database adapter initialized during framework startup. |
| `queue` | Mutable runtime component | Database-backed transaction queue facade initialized on first transaction fetch. |
| `repo` | Mutable runtime component | Repository handler may cache locator files and update internal runtime state. |
| `driver` | Mutable runtime component | Driver wrapper owns browser lifecycle and may restart during recovery or app switch. |
| `logs` | Mutable trace list | In-memory execution trace used for tests and execution summaries; operational logging is handled by the logging framework. |

### 3.4 State Rules

- State shall be the single source of truth for execution flow.
- Runtime nodes shall remain thin and delegate state updates to the service layer.
- Service modules shall update only the state fields they own.
- Configuration sections shall be treated as read-only after initialization.
- Runtime state shall drive LangGraph routing decisions.
- Driver, repository, runtime modules, and automation steps shall be accessed through state instead of recreated directly by business logic.

## 4. Initialization Model

Initialization is split into two lifecycle levels: framework initialization and execution initialization.

### 4.1 Framework Initialization

Framework initialization runs once per framework execution.

Responsibilities:

- Load framework-level and execution-level configuration.
- Initialize logging and observability.
- Initialize the queue adapter placeholder.
- Initialize the object repository manager.
- Initialize the runtime module loader and automation step loader.
- Create the initial shared state shell.
- Validate required framework configuration.
- Start the LangGraph execution flow.

Framework initialization shall not be repeated for normal transaction retry.

### 4.2 Execution Initialization

Execution initialization runs at the start of an app/process execution cycle and may run again during runtime.

Responsibilities:

- Coordinate application-session startup, batch completion, application switching, retry recovery, and master-queue refresh.
- Use `runtime_config.execution_init_reason` to select the required behavior.
- Execute the optional project-specific `EXECUTION_INIT` KeySteps hook for the active application when a session reset is required.
- Keep application-specific close/reset behavior outside the framework.
- Reset `application_logged_in` and the per-session batch counter when a session is restarted.
- Advance to the next ordered `PROCESS_TRANSACTION` application after `BATCH_COMPLETE` or `APP_SWITCH`.
- Preserve the current transaction and active application during `RETRY`.

Execution initialization may be triggered by:

- Initial process/app execution start.
- System exception retry.
- Application switch.
- Browser or session recovery.
- Framework-controlled restart of the execution cycle.
- Completed application batch.
- Scheduled master-queue refresh.

## 5. Configuration Management

### 5.1 Source

Configuration shall be loaded from a shared config library.

### 5.2 `execution_config`

Execution configuration contains framework execution control parameters:

- `retry_limit`
- `wait_enabled`
- `wait_limit`
- `wait_seconds`

Transaction batch limits are read from each `PROCESS_TRANSACTION` KeySteps row's `BatchCount`, not from the legacy global `batch_enabled` or `batch_limit` settings.

### 5.3 `process_config`

Process configuration contains process/app-specific settings:

- active application or process identifier
- object repository base path
- init module file path or identifier
- process module file path or identifier
- automation steps Excel/CSV file path
- queue creation flag
- `master_queue_interval_hours`
- login/session settings
- application-specific settings

### 5.4 `logging_config`

Logging configuration contains execution-scoped logging settings:

- `level`
- `log_file`
- `console`
- `max_bytes`
- `backup_count`

### 5.5 Configuration Rules

- Configuration shall be loaded during initialization only.
- Configuration shall not be reloaded during transaction processing.
- Configuration shall not be modified at runtime.
- Process/app selection may update which read-only `process_config` is active for the execution cycle.
- Relative config paths shall resolve from the configuration file location.

## 5.6 Shared Common Utilities

The shared root may contain a constant `common` folder for reusable utilities that are not specific to one application or automation process.

Current convention:

```text
<share_root>/
  common/
    exceptions.py
    excel.py
```

Rules:

- `share/common` is for cross-process helper code only.
- App-specific helpers remain under the app's own shared folder, for example `share/config/apps/<app>/shared`.
- Shared utilities shall not update LangGraph state directly.
- Shared utilities shall raise clear utility exceptions; runtime/process code maps those exceptions to framework outcomes such as `SYSTEM_EXCEPTION`.
- The initial Excel utility reads `.xlsx` files in read-only mode and returns a `pandas.DataFrame`.
- The framework does not currently add `share_root` to `sys.path` for `common`; dynamic loading/import strategy will be decided separately.

## 6. Driver Management

### 6.1 Design

The framework shall use a single driver wrapper object encapsulating:

- Playwright engine
- Browser instance
- Browser context
- Active page

### 6.2 Driver Lifecycle

| Stage | Behavior |
| --- | --- |
| Framework initialization | Prepare driver services and lifecycle dependencies. |
| Execution initialization | Create or restart the active driver as needed. |
| Process transaction | Reuse the same driver for transaction execution. |
| System exception | Restart driver through execution initialization. |
| Application switch | Restart driver through execution initialization. |
| End | Stop driver and release resources. |

### 6.3 Driver Rules

- Only one active driver shall exist per execution cycle.
- The driver shall not be recreated per transaction.
- Driver restart shall occur only for system exception recovery, application switch, or framework-controlled execution restart.
- Business process code shall use the framework-provided driver wrapper.

### 6.4 Driver Responsibilities

The driver wrapper shall:

- Manage browser lifecycle.
- Provide access to the active page.
- Handle restart and cleanup.
- Support future extensions such as multi-tab handling, tracing, screenshots, and diagnostics.

## 7. Object Repository

### 7.1 Design

The object repository shall be:

- Stored in a shared location.
- Loaded dynamically at runtime.
- Organized by application and page.
- Cached in memory by the repository handler.

### 7.2 Path Convention

```text
{base_path}/{app}/{page}.json
```

### 7.3 Locator Structure

Each repository element shall support:

- primary locator
- secondary locator fallback

### 7.4 Repository Rules

- Repository files shall be loaded on demand.
- Repository data shall be cached in memory.
- Locators shall not be hardcoded in process or framework code.
- Runtime module functions shall access locators through the framework-provided repository handler.

## 8. Runtime Modules and Automation Steps

### 8.1 Design

The framework shall dynamically load the process callable configured for the active queue application's `PROCESS_TRANSACTION` KeySteps row.

The runtime execution model shall use:

- `KeySteps.xlsx` loaded once during `FRAMEWORK_INIT`
- the active transaction's `queue_application_details` as the application selector
- `State = PROCESS_TRANSACTION` and `Application` to select matching rows
- numeric `Sequence` ordering when more than one row matches
- a `Module` value in `package.module:function` format
- a `BatchCount` value where blank or zero means all eligible work and a positive integer is the session limit
- lazy import and invocation during `PROCESS_TRANSACTION`

### 8.2 Responsibility Split

| Owner | Responsibilities |
| --- | --- |
| Framework | Orchestration, lifecycle, retry, state, driver, repository, config, queue interaction, dynamic module loading, step execution, logging, result handling, and transitions. |
| Services | Implement node behavior behind thin LangGraph node wrappers. |
| Application Runtime | Owns login/session preparation before process execution. The current login implementation is a lifecycle placeholder. |
| Process Module | Exposes the callable named by the KeySteps `Module` value and returns a framework-compatible result. |
| KeySteps | Selects process application, execution sequence, state, and module callable. |

### 8.3 Config-Driven Step Model

The framework shall support a KeySteps-driven process execution model:

- The active project configuration directory contains `KeySteps.xlsx`.
- The framework matches `PROCESS_TRANSACTION` rows to the current queue application.
- The selected row explicitly identifies the importable module and callable.
- Matching rows are resolved in numeric sequence order; the current implementation executes the first matching row.
- The process callable is imported only when the process node executes.
- Runtime module functions execute using framework-provided state, driver wrapper, object repository, and configuration.
- Runtime module functions shall not own orchestration, retry, queue updates, or graph routing.

### 8.4 Automation Step Contract

Each automation step shall provide enough information for deterministic runtime resolution.

Required process-step fields:

- `Sequence`
- `State`
- `BatchCount`
- `Application`
- `Module`

Example:

```text
Sequence | State               | BatchCount | Application | Module
1        | PROCESS_TRANSACTION | 3          | 12          | image_value_extraction.runtime:run_process
```

An optional project-specific application reset hook uses the same callable format:

```text
Sequence | State          | Application | Module
1        | EXECUTION_INIT | 12          | image_value_extraction.runtime:reset_application
```

The reset hook receives the shared state. It is called for `BATCH_COMPLETE`, `APP_SWITCH`, and `RETRY`; it is not called during normal `STARTUP` or a master-queue refresh.

### 8.5 Function Contract

Loaded functions shall accept the shared state and may use framework-provided driver, repository, and configuration through that state.

Example function style:

```python
def run_process(state):
    return {
        "outcome": "SUCCESS",
        "message": "Document processed",
        "data": {"output_path": "..."},
        "next_action": None,
    }
```

Each executed step shall produce a framework-readable `StepResult`.

`StepResult` fields:

| Field | Meaning |
| --- | --- |
| `outcome` | Required process outcome: `SUCCESS`, `BUSINESS_EXCEPTION`, or `SYSTEM_EXCEPTION`. |
| `message` | Optional human-readable message or error detail. |
| `data` | Optional output data from the step. |
| `next_action` | Optional routing hint for framework-controlled transitions such as app switch. |

The process callable must return a mapping compatible with `StepResult`. Missing, unsupported, or malformed results are converted to `SYSTEM_EXCEPTION` by the process runtime.

## 9. Queue Management

### 9.1 Design

The framework shall use a DB-driven queue as the source of transactions. The local implementation shall use SQLite to manage the queue while replicating the production DB table model. The framework shall keep DB access behind the queue adapter/runtime boundary so locking, status updates, and future schema refinements do not leak into LangGraph nodes or process automation modules.

The current schema baseline is `docs/db_Schema_Full.sql`, captured from MySQL 8.0.35 database `rpa_test_new` on 2026-05-15 using a no-data dump for:

- `tbl_institution`
- `tbl_botlist`
- `tbl_input`
- `tbl_process`
- `tbl_login_process_link`
- `tbl_output`
- `tbl_login`
- `tbl_application`
- `tbl_queue`

The older `docs/db_Schema.txt` dump is partially truncated around `tbl_process` and `tbl_queue`; implementations shall prefer `docs/db_Schema_Full.sql` when creating the SQLite schema.

### 9.2 Transaction States

The intended transaction lifecycle is configurable. The confirmed in-progress value is `In Processing`; queue-created and final success/fail/skip values shall be read from configuration so production naming can be matched exactly.

```text
<eligible status> -> In Processing -> <success / skipped / failed status>
```

### 9.3 Schema Overview

#### Institution and Process

`tbl_institution` stores institution master data.

| Column | Type | Notes |
| --- | --- | --- |
| `ID` | `mediumint` | Primary key, auto-increment. |
| `Ins_Name` | `varchar(1000)` | Required institution name. |
| `Ins_BU` | `mediumtext` | Business unit details. |
| `Ins_Mid` | `mediumtext` | MID details. |

`tbl_process` stores process definitions for institutions.

| Column | Type | Notes |
| --- | --- | --- |
| `ID` | `mediumint` | Primary key, auto-increment. |
| `Process_Name` | `varchar(255)` | Required process name. |
| `Ins_ID` | `mediumint` | Required institution reference. |

Relationship:

- `tbl_process.Ins_ID` references `tbl_institution.ID`.

#### Applications and Bots

`tbl_application` is the application or processor master table.

| Column | Type | Notes |
| --- | --- | --- |
| `ID` | `mediumint` | Primary key, auto-increment. |
| `App_Name` | `varchar(100)` | Required application name. |

`tbl_botlist` stores bot inventory/status.

| Column | Type | Notes |
| --- | --- | --- |
| `ID` | `bigint` | Primary key, auto-increment. |
| `BotName` | `tinytext` | Required bot name. |
| `BotDescription` | `text` | Optional description. |
| `BotStatus` | `tinytext` | Required bot status. |

#### Input Cases

`tbl_input` is the main incoming case/chargeback table and is the source case record for queue processing.

| Column | Type | Notes |
| --- | --- | --- |
| `ID` | `bigint` | Primary key, auto-increment. |
| `Processor` | `mediumint` | Required application/processor reference. |
| `Process` | `mediumint` | Required process reference. |
| `Case_Number` | `varchar(100)` | Optional case number. |
| `Transaction_ID` | `varchar(100)` | Optional transaction identifier. |
| `Case_Status` | `varchar(100)` | Optional source case status. |
| `Chargeback_Date` | `date` | Required chargeback date. |
| `Case_Json` | `json` | Required source payload. |
| `Transaction_Amount` | `varchar(100)` | Optional transaction amount. |
| `Mid_Alias` | `varchar(100)` | Optional MID alias. |
| `MID_Number` | `varchar(100)` | Optional MID number. |
| `Case_ID` | `varchar(100)` | Required case identifier. |
| `Chargeback_Amount` | `varchar(100)` | Optional chargeback amount. |
| `Transaction_Date` | `date` | Optional transaction date. |
| `Deadline_Date` | `date` | Optional deadline date. |
| `Card_First_Six` | `varchar(100)` | Optional first six card digits. |
| `Card_Last_Four` | `varchar(100)` | Optional last four card digits. |
| `Card_Type` | `varchar(100)` | Optional card type. |
| `Status` | `varchar(100)` | Optional processing/source status. |
| `QueueCreation_timestamp` | `datetime` | Optional queue creation timestamp. |
| `Input_Identifier` | `varchar(100)` | Optional unique input identifier. |
| `Institution` | `varchar(100)` | Optional denormalized institution name/code. |
| `BUnit` | `varchar(100)` | Optional denormalized business unit. |

Relationships and indexes:

- `tbl_input.Process` references `tbl_process.ID`.
- `tbl_input.Processor` references `tbl_application.ID`.
- `Input_Identifier` is unique.
- Indexed lookup paths include `Status`, `Case_Number`, `Case_ID + Process`, and a composite index over `ID`, `Process`, `Case_Number`, `Transaction_ID`, `Input_Identifier`, and `QueueCreation_timestamp`.

#### Queue

`tbl_queue` manages processing work items for input cases.

| Column | Type | Notes |
| --- | --- | --- |
| `ID` | `bigint` | Primary key, auto-increment. |
| `Case_Details` | `bigint` | Input case reference. |
| `Application_Details` | `mediumint` | Application reference. |
| `Bot_Name` | `varchar(100)` | Optional assigned bot name. |
| `Processing_Status` | `varchar(100)` | Queue processing state. |
| `CTO_Details` | `json` | Optional runtime/details JSON. |
| `Evidence_Status` | `json` | Optional evidence status JSON. |
| `Output_tbl_Status` | `tinyint(1)` | Optional output table flag/status. |
| `Bot_Comment` | `text` | Optional runtime comment or reason. |
| `Dependency` | `json` | Optional dependency JSON. |
| `ProcessingSTART_timestamp` | `datetime` | Optional processing start timestamp. |
| `ProcessingEND_timestamp` | `datetime` | Optional processing end timestamp. |

Relationships and indexes:

- `tbl_queue.Case_Details` references `tbl_input.ID`.
- `tbl_queue.Application_Details` references `tbl_application.ID`.
- Indexed lookup paths include `Processing_Status` and a composite index over `ID`, `Case_Details`, and `Application_Details`.

#### Login and Output Tables

The no-data dump command included `tbl_login`, `tbl_login_process_link`, and `tbl_output`, but their `CREATE TABLE` sections were not present in the pasted text. The intended model is:

- `tbl_login` stores application login/session configuration.
- `tbl_login_process_link` links login records to process/application execution requirements.
- `tbl_output` stores transaction processing results or downstream output payloads.

The complete schema for these tables must be captured before implementation relies on them.

### 9.4 Queue Adapter Rules

- Each transaction shall be locked before processing.
- Duplicate processing shall be prevented.
- Failed transactions shall be recorded with a reason.
- Queue selection shall prioritize records eligible by `Processing_Status`.
- Runtime queue selection shall filter eligible records by `runtime_config.active_application_id`.
- The queue adapter shall also provide a global eligible-record check used to decide whether the scheduler must switch applications or finish.
- Queue records shall retain a durable link to `tbl_input.ID`.
- Master queue creation shall accept supplied items as a DataFrame, whether the upstream source is Excel or an API call.
- Master queue creation shall insert input details into `tbl_input`, including the full detail payload in `Case_Json`, then create one linked `tbl_queue` row for each distinct application in the sequenced `PROCESS_TRANSACTION` KeySteps.
- Queue creation shall consider only inputs for the configured process whose status is null or blank. The complete application queue set and the input's queue-created status/timestamp shall commit atomically per input.
- `tbl_input.Input_Identifier` remains the database-enforced idempotency key. When an input identifier already exists, master queue loading shall roll back that row, record it as skipped, log the expected condition at `INFO` without a traceback, and continue. It shall not classify the duplicate as a failed input.
- Non-duplicate database insert failures shall remain failed rows and shall be logged at `ERROR` with exception details.
- Runtime transaction context shall include queue fields, input fields, and parsed `tbl_input.Case_Json` for process use.
- `get_transaction` shall mark the selected queue item as `In Processing` and set `ProcessingSTART_timestamp`.
- `process_transaction` may update runtime queue columns such as `CTO_Details`, `Evidence_Status`, `Dependency`, `Bot_Comment`, and `Output_tbl_Status`.
- `transition_hub` shall update final configured status and `ProcessingEND_timestamp`.
- The framework shall not directly query these tables from LangGraph nodes or process modules; all DB interaction shall go through the queue/runtime adapter boundary.
- Locking strategy, transaction isolation, final status vocabulary, and exact update SQL remain implementation details to confirm from production operating rules.

## 10. LangGraph Workflow

### 10.1 States

The workflow shall include the following logical nodes:

- `FRAMEWORK_INIT`
- `EXECUTION_INIT`
- `MASTER_QUEUE_CREATOR`
- `MASTER_QUEUE_WAIT`
- `GET_TRANSACTION`
- `LOGIN_APPLICATION`
- `PROCESS_TRANSACTION`
- `TRANSITION_HUB`
- `END`

### 10.2 Flow Logic

#### FRAMEWORK_INIT

- Load framework and execution configuration.
- Initialize logging and shared services.
- Delegate framework startup behavior to the framework lifecycle service.
- Initialize queue adapter placeholder.
- Create the shared state shell.
- Route to `EXECUTION_INIT`.

#### EXECUTION_INIT

- Delegate to `framework.runtime.execution_init_runtime.initialize_execution`.
- On `STARTUP`, retain the first process application selected during framework initialization.
- On `BATCH_COMPLETE` or `APP_SWITCH`, run the current application's optional reset hook, reset its session, and activate the next ordered process step.
- On `RETRY`, run the current application's optional reset hook, reset the application session, and preserve the active transaction and application.
- On `MASTER_QUEUE_REFRESH`, retain the application session without running the reset hook.
- Convert reset-hook loading or execution failures to `SYSTEM_EXCEPTION` and request `END`.

#### MASTER_QUEUE_CREATOR

- If `masterbot` is false, never populate the queue.
- If `masterbot` is true and `master_queue_interval_hours` is blank or zero, populate once per framework execution.
- If `masterbot` is true and `master_queue_interval_hours` is positive, populate at startup and whenever the interval has elapsed.
- Record successful run count and UTC completion time; failed runs are not counted.
- Delegate queue creation behavior to the queue runtime service.

#### MASTER_QUEUE_WAIT

- Used only when periodic masterbot scheduling is enabled, the queue is globally empty, and the next master run is not due.
- Sleep for the positive `execution_config.wait_seconds` polling interval.
- Route back through `EXECUTION_INIT` with reason `MASTER_QUEUE_REFRESH`.
- Reject blank, zero, negative, or nonnumeric polling intervals to prevent a busy loop.

#### GET_TRANSACTION

- Fetch the next transaction.
- Lock the transaction as `IN_PROGRESS`.
- Fetch only for `runtime_config.active_application_id`.
- Store the current transaction in `runtime_config.txn`.
- If no transaction exists, store `NO_TRANSACTION` in runtime state and route to `TRANSITION_HUB`.
- When a transaction is found, reset `runtime_config.wait_count` to `0`.
- Delegate transaction retrieval behavior to the queue runtime service.

#### LOGIN_APPLICATION

- Check whether application login has already completed for the current execution.
- If login already completed, route directly to `PROCESS_TRANSACTION`.
- If login has not completed, perform application login, set `runtime_config.application_logged_in` to `true`, and route to `PROCESS_TRANSACTION`.
- Delegate login behavior to the application runtime service.

#### PROCESS_TRANSACTION

The framework executes the current transaction by selecting the matching `PROCESS_TRANSACTION` row from the loaded `KeySteps.xlsx` DataFrame. Matching uses the active transaction's `queue_application_details` value and the KeySteps `Application` column. Matching rows are ordered by numeric `Sequence`, and the first row is selected.

The selected `Module` value shall use `package.module:function` format. For example:

```text
image_value_extraction.runtime:run_process
```

The configured callable shall receive the complete shared state and return a mapping containing `outcome` plus optional `message`, `data`, and `next_action` values. Process execution behavior shall be delegated to `framework.runtime.process_runtime`.

| Outcome | Action |
| --- | --- |
| `SUCCESS` | Store the outcome in runtime state and route to `TRANSITION_HUB`. |
| `BUSINESS_EXCEPTION` | Store the outcome and error in runtime state and route to `TRANSITION_HUB`. |
| `SYSTEM_EXCEPTION` | Store the outcome and error in runtime state and route to `TRANSITION_HUB`. |

`PROCESS_TRANSACTION` shall not directly decide the next graph node. Post-processing decisions are centralized in `TRANSITION_HUB`.

System exception retry logic:

```text
if retry_count < retry_limit:
    increment retry_count
    TRANSITION_HUB routes to EXECUTION_INIT for recovery
    EXECUTION_INIT resets the same application
    route directly to LOGIN_APPLICATION with the same transaction
else:
    if an active transaction exists:
        mark transaction FAILED
        TRANSITION_HUB routes to GET_TRANSACTION or END based on runtime controls
    else:
        TRANSITION_HUB routes to END
```

#### TRANSITION_HUB

Handles transaction status updates and routing decisions for:

- marking successful transactions as `SUCCESS`
- marking business exceptions as `SKIPPED`
- marking system exceptions as `FAILED` after retry exhaustion
- batch completion
- no queue condition
- application switch
- wait logic
- retry recovery
- end condition
- transition behavior shall be delegated to the transition runtime service
- increment `session_batch_count` only after a transaction is finalized as success, skipped, or final failure
- route a completed positive batch through `EXECUTION_INIT`; batch completion does not directly mean `END`
- when the active application has no work but eligible records exist globally, request `APP_SWITCH`
- route to `END` only after application-session reset when no eligible queue work and no periodic masterbot wait remain

### 10.3 Graph Routing Contract

The graph shall use `TRANSITION_HUB` as the central post-transaction decision node.

| From Node | Condition | To Node |
| --- | --- | --- |
| `FRAMEWORK_INIT` | Initialization succeeds | `EXECUTION_INIT` |
| `FRAMEWORK_INIT` | Initialization fails and requests `END` | `END` |
| `EXECUTION_INIT` | Retry recovery succeeds | `LOGIN_APPLICATION` |
| `EXECUTION_INIT` | Master queue is due | `MASTER_QUEUE_CREATOR` |
| `EXECUTION_INIT` | Eligible queue work exists | `GET_TRANSACTION` |
| `EXECUTION_INIT` | Queue empty and periodic masterbot is not yet due | `MASTER_QUEUE_WAIT` |
| `EXECUTION_INIT` | Queue empty and no periodic run remains | `END` |
| `MASTER_QUEUE_WAIT` | Polling wait completes | `EXECUTION_INIT` |
| `MASTER_QUEUE_CREATOR` | Queue creation completes | `GET_TRANSACTION` |
| `MASTER_QUEUE_CREATOR` | Queue creation fails and requests `END` | `END` |
| `GET_TRANSACTION` | Transaction found | `LOGIN_APPLICATION` |
| `GET_TRANSACTION` | No transaction | `TRANSITION_HUB` |
| `LOGIN_APPLICATION` | Login already completed or login completed now | `PROCESS_TRANSACTION` |
| `PROCESS_TRANSACTION` | Always after storing result | `TRANSITION_HUB` |
| `TRANSITION_HUB` | Success/business exception and more work allowed | `GET_TRANSACTION` |
| `TRANSITION_HUB` | No transaction and wait is enabled/remaining | `GET_TRANSACTION` |
| `TRANSITION_HUB` | Active application empty but eligible work exists globally | `EXECUTION_INIT` for `APP_SWITCH` |
| `TRANSITION_HUB` | No eligible transaction remains globally | `EXECUTION_INIT` for session completion |
| `TRANSITION_HUB` | System exception and retry remains | `EXECUTION_INIT` |
| `TRANSITION_HUB` | System exception, retries exhausted, and no active transaction | `END` |
| `TRANSITION_HUB` | Application switch required | `EXECUTION_INIT` |
| `TRANSITION_HUB` | Active application batch limit reached | `EXECUTION_INIT` for `BATCH_COMPLETE` |

#### END

- Close the driver.
- Release resources.
- Complete final logging.
- Set `runtime_config.next_action` to `END` so the returned terminal state is unambiguous.

## 11. Runtime Control

### 11.1 `runtime_config` Fields

| Field | Purpose |
| --- | --- |
| `retry_count` | Tracks system retry attempts. |
| `batch_count` | Legacy total fetched-transaction counter retained for compatibility and diagnostics. |
| `process_steps` | Ordered validated `PROCESS_TRANSACTION` definitions loaded from KeySteps. |
| `active_process_step_index` | Identifies the active ordered process step. |
| `active_application_id` | Application ID used to filter transaction fetches. |
| `active_batch_limit` | Positive KeySteps batch limit, or `None` for all eligible work. |
| `session_batch_count` | Number of finalized transactions in the active application session. |
| `execution_init_reason` | Current coordinator reason such as `STARTUP`, `BATCH_COMPLETE`, `APP_SWITCH`, `RETRY`, or `MASTER_QUEUE_REFRESH`. |
| `master_queue_run_count` | Number of successful master-queue runs in this framework execution. |
| `master_queue_last_run_at` | Timezone-aware UTC completion time of the latest successful master-queue run. |
| `wait_count` | Tracks idle wait attempts when no transaction is available. |
| `application_logged_in` | Tracks whether application login has completed for the current execution. |
| `txn` | Holds the current transaction. |
| `last_status` | Stores latest execution outcome such as `SUCCESS`, `SKIPPED`, or `FAILED`. |
| `last_error` | Stores latest error details. |
| `next_action` | Controls LangGraph routing. |

### 11.2 Runtime Rules

- Runtime fields shall be updated by services called by nodes.
- Runtime fields shall drive LangGraph transitions.
- Transaction-specific runtime data shall be cleared or reset when moving to the next transaction.
- Retry counters shall be reset after successful recovery or after final transaction failure, as defined during implementation.

### 11.3 Allowed `next_action` Values

| Value | Meaning |
| --- | --- |
| `PROCESS` | `GET_TRANSACTION` found a transaction and should route to `PROCESS_TRANSACTION`. |
| `GET_TRANSACTION` | The framework should fetch the next transaction. |
| `RETRY` | A system exception can still retry and should route to `EXECUTION_INIT`. |
| `APP_SWITCH` | The active app/process must change and should route to `EXECUTION_INIT`. |
| `BATCH_COMPLETE` | The active application session must close/reset before selecting the next process step. |
| `MASTER_QUEUE_REFRESH` | The periodic schedule should be checked through `EXECUTION_INIT`. |
| `END` | Execution should route to `END`. |

## 12. Exception Handling

### 12.1 Exception Types

| Type | Meaning | Framework Action |
| --- | --- | --- |
| Business Exception | Expected process or validation failure for a transaction. | Mark transaction as `SKIPPED`; do not retry. |
| System Exception | Browser, infrastructure, app availability, or framework-level failure. | Retry through execution initialization, then fail if retry limit is reached. |

### 12.2 Exception Rules

- Only system exceptions shall trigger retry.
- Business exceptions shall not trigger retry.
- All errors shall be logged.
- System exception recovery shall restart through execution initialization, not full framework initialization.
- Final failure shall record the error reason.

## 13. Logging

### 13.1 Design

The framework shall use Python logging for operational logs and maintain a lightweight in-memory state trace for tests and run summaries.

Logging shall:

- start before graph execution begins
- end after graph execution completes or fails
- support log levels such as `DEBUG`, `INFO`, `WARNING`, and `ERROR`
- log variable values at `DEBUG` level where useful for troubleshooting
- support console output when enabled
- support rotating file logs using configured file size and backup count
- record unhandled framework execution errors with stack traces
- record node entry, lifecycle progress, and transition outcomes at `INFO`
- keep detailed configuration, transaction, application, queue, and process values at `DEBUG`
- restrict transaction-fetch `DEBUG` messages to `queue_id`, `input_id`, and `application_id`
- restrict transition-input `DEBUG` messages to outcome, queue ID, retry count, batch count, wait count, and requested action
- restrict execution-initialization and scheduler `DEBUG` messages to safe operational fields such as reason, application IDs, limits, counts, timestamps, and selected module
- do not dump the complete runtime dictionary while waiting for transactions
- record handled business failures at `WARNING`
- record handled technical failures at `ERROR`
- record unexpected raised exceptions with the exception message and traceback
- avoid logging document contents and extracted OCR output
- prevent customer data, parsed case payloads, process results, and OCR values from being interpolated into transaction-fetch or transition-input messages

### 13.2 Logging Configuration

`logging_config` shall support:

| Field | Purpose |
| --- | --- |
| `level` | Minimum log level. |
| `log_file` | Path to the active log file. |
| `console` | Whether logs should also be written to console. |
| `max_bytes` | Maximum log file size before rotation. |
| `backup_count` | Number of rotated log files to retain. |

## 14. Non-Functional Requirements

### 14.1 Reliability

- Prevent duplicate transaction processing.
- Support deterministic state-driven transitions.
- Preserve enough runtime context for recovery decisions.

### 14.2 Performance

- Reuse browser session within an execution cycle.
- Avoid recreating the driver per transaction.
- Lazy load repository data.
- Cache repository files where appropriate.

### 14.3 Maintainability

- Keep behavior config-driven.
- Keep locators externalized.
- Keep process-specific automation logic outside the framework core.
- Keep framework orchestration independent from process implementation details.
- Keep LangGraph nodes thin and delegate implementation behavior to services.

### 14.4 Observability

- Log every state transition.
- Track transaction lifecycle.
- Capture error details.
- Support execution-scoped logging configuration.
- Support log level control for debug values.
- Support console logging when enabled.
- Support rotating file logs with configurable maximum size and backup count.
- Preserve a lightweight in-memory state trace for tests and summaries.
- Support future diagnostics such as screenshots, traces, and execution summaries.

## 15. Final Summary

The Orqflow framework shall provide a state-driven automation foundation where:

- **LangGraph** controls flow.
- **Nodes** provide thin graph-facing wrappers.
- **Services** own node behavior and runtime updates.
- **State** carries runtime and service context.
- **Driver** handles Playwright browser execution.
- **Repository** provides dynamic locators.
- **Config** controls framework and process behavior.
- **Logging Config** controls operational logging and rolling files.
- **Queue** feeds transactions through a SQLite-backed model that mirrors the production queue/input schema.
- **Runtime Modules** supply configured init and process functions.
- **Automation Steps** drive keyword-based function execution from Excel/CSV definitions.

The target outcome is a deterministic, scalable, config-driven automation framework that supports retries, batching, multi-app execution, runtime module loading, Excel/CSV-driven keyword steps, and clean separation of framework and process responsibilities.
