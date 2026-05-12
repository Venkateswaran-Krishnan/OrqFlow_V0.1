# Orqflow Automation Framework Requirements

## 1. Objective

Build a state-driven automation framework for RPA-style browser automation using:

- **LangGraph** for orchestration and state-machine flow control.
- **Playwright** as the browser automation execution engine.
- **Shared Config Library** for centralized configuration.
- **Shared Object Repository** for dynamic locator management.
- **DB Queue** as the transaction source. Queue details are intentionally kept as a placeholder for later design.

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
       GET_TRANSACTION
       PROCESS_TRANSACTION
       TRANSITION_HUB
       END
  -> Service Layer
       Framework Lifecycle Service
       Execution Lifecycle Service
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
| Queue Adapter | Provides transaction retrieval and status updates. Detailed DB design is deferred. |
| Runtime Modules | Contains configured init and process function files loaded at the appropriate lifecycle point. |
| Automation Steps | Excel/CSV-driven step definitions that explicitly map keywords to functions. |

### 2.2 Service Layer

The framework shall keep LangGraph node functions thin. Each node function shall log the node event and delegate behavior to a service module.

Current service responsibilities:

| Service | Responsibility |
| --- | --- |
| `framework_lifecycle` | Framework-level startup behavior such as queue adapter initialization. |
| `execution_lifecycle` | Execution-cycle setup, init module loading, automation step loading, repository setup, driver start/restart, and init-step execution. |
| `queue_runtime` | Master queue creation placeholder, transaction fetch, wait handling, batch counter updates, and transaction assignment to runtime state. |
| `transaction_runtime` | Process-module lazy loading for the active app/process and process-step execution. |
| `transition_runtime` | Transaction status updates and post-process routing decisions. |
| `cleanup_runtime` | Driver shutdown and execution cleanup. |
| `runtime_state` | Shared helpers for storing step results, clearing process runtime, loading process modules, and deciding next transaction/end behavior. |

## 3. State Management

### 3.1 Principle

The system shall maintain a single shared state object passed across all LangGraph nodes. The state is the single source of truth for orchestration, runtime decisions, current transaction context, driver access, repository access, and process execution state.

### 3.2 State Sections

```text
state
  execution_config
  process_config
  logging_config
  runtime_config
    retry_count
    batch_count
    wait_count
    txn
    last_status
    last_error
    next_action
  repo
  driver
  init_module
  process_module
  process_module_app
  automation_steps
  logs
```

### 3.3 Mutability Rules

| State Section | Mutability | Rule |
| --- | --- | --- |
| `execution_config` | Read-only | Loaded during initialization and not modified by runtime nodes. |
| `process_config` | Read-only | Selected during execution initialization and not modified during transaction processing. |
| `logging_config` | Read-only | Loaded from config and used to configure execution-scoped logging before the graph is invoked. |
| `runtime_config` | Mutable | Updated by services to track retries, batch counts, wait counts, transaction context, errors, and routing actions. |
| `repo` | Mutable runtime component | Repository handler may cache locator files and update internal runtime state. |
| `driver` | Mutable runtime component | Driver wrapper owns browser lifecycle and may restart during recovery or app switch. |
| `init_module` | Mutable runtime component | Runtime-loaded init/setup function module for the active process/app execution cycle. |
| `process_module` | Mutable runtime component | Runtime-loaded process function module for transaction execution, loaded by `PROCESS_TRANSACTION`. |
| `process_module_app` | Mutable runtime marker | Identifies which app/process the loaded `process_module` belongs to. |
| `automation_steps` | Mutable runtime component | Loaded Excel/CSV step definitions used to drive init and process function execution. |
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

- Select or load the active process/app configuration.
- Dynamically load the configured init module based on process/app config.
- Clear any previously loaded process module/app marker so `PROCESS_TRANSACTION` can load the process module for the active app/process.
- Load and validate the configured Excel/CSV automation steps file.
- Initialize or restart the Playwright driver wrapper.
- Load or refresh app-specific repository context.
- Perform login or session setup by executing configured init steps/functions when required by the active process/app.
- Reset runtime counters and transaction context where appropriate.
- Prepare shared state for transaction processing.

Execution initialization may be triggered by:

- Initial process/app execution start.
- System exception retry.
- Application switch.
- Browser or session recovery.
- Framework-controlled restart of the execution cycle.

## 5. Configuration Management

### 5.1 Source

Configuration shall be loaded from a shared config library.

### 5.2 `execution_config`

Execution configuration contains framework execution control parameters:

- `retry_limit`
- `batch_enabled`
- `batch_limit`
- `wait_enabled`
- `wait_limit`
- `wait_seconds`

### 5.3 `process_config`

Process configuration contains process/app-specific settings:

- active application or process identifier
- object repository base path
- init module file path or identifier
- process module file path or identifier
- automation steps Excel/CSV file path
- queue creation flag
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

The framework shall dynamically load configured runtime modules and automation steps based on lifecycle ownership and the active process/app configuration.

The runtime execution model shall use:

- an init module containing setup, login, session, and pre-check functions
- a process module containing process-specific transaction functions
- an Excel/CSV automation steps file that defines execution order and explicitly maps each keyword step to a function
- init modules are loaded during `EXECUTION_INIT`
- process modules are lazy-loaded during `PROCESS_TRANSACTION` and associated with `process_module_app`

### 8.2 Responsibility Split

| Owner | Responsibilities |
| --- | --- |
| Framework | Orchestration, lifecycle, retry, state, driver, repository, config, queue interaction, dynamic module loading, step execution, logging, result handling, and transitions. |
| Services | Implement node behavior behind thin LangGraph node wrappers. |
| Init Module | Callable setup functions such as login, session preparation, app readiness checks, and execution-cycle preparation. |
| Process Module | Callable process-specific functions used during transaction execution. |
| Automation Steps | Excel/CSV step definitions that control execution order and map keywords to module functions. |

### 8.3 Config-Driven Step Model

The framework shall support a config-driven step execution model:

- The active process/app config identifies the init module, process module, and automation steps file.
- Automation steps are maintained in Excel/CSV format.
- Each step explicitly identifies the source module and function to execute.
- The framework resolves and executes steps in order.
- The process module is loaded only when process steps are executed and is invalidated during execution reinitialization/app switch.
- Runtime module functions execute using framework-provided state, driver wrapper, object repository, and configuration.
- Runtime module functions shall not own orchestration, retry, queue updates, or graph routing.

### 8.4 Automation Step Contract

Each automation step shall provide enough information for deterministic runtime resolution.

Minimum step fields:

- `order`
- `phase`
- `keyword`
- `source`, such as `init` or `process`
- `function_name`
- `parameters`
- `on_error`

Example conceptual steps:

```text
order | keyword          | source  | function_name       | parameters
1     | login            | init    | login               | ...
2     | prepare_session  | init    | prepare_session     | ...
3     | open_case        | process | open_case           | ...
4     | validate_data    | process | validate_data       | ...
5     | submit           | process | submit_transaction  | ...
```

### 8.5 Function Contract

Loaded functions shall accept the shared state and may use framework-provided driver, repository, and configuration through that state.

Example conceptual function style:

```python
def login(state):
    ...

def open_case(state):
    ...

def submit_transaction(state):
    ...
```

Each executed step shall produce a framework-readable `StepResult`.

`StepResult` fields:

| Field | Meaning |
| --- | --- |
| `outcome` | Execution outcome such as `SUCCESS`, `BUSINESS_EXCEPTION`, `SYSTEM_EXCEPTION`, `NO_TRANSACTION`, or `END`. |
| `message` | Optional human-readable message or error detail. |
| `data` | Optional output data from the step. |
| `next_action` | Optional routing hint for framework-controlled transitions such as app switch. |

Step functions may return `None`, an outcome string, an outcome enum, or a dictionary compatible with `StepResult`. The framework shall normalize the return value into `StepResult`.

## 9. Queue Management

### 9.1 Design

The framework shall use a DB-driven queue as the source of transactions. The queue design is a placeholder in the current version and shall be refined later.

### 9.2 Transaction States

The intended transaction lifecycle is:

```text
READY -> IN_PROGRESS -> SUCCESS / SKIPPED / FAILED
```

### 9.3 Placeholder Rules

- Each transaction shall be locked before processing.
- Duplicate processing shall be prevented.
- Failed transactions shall be recorded with a reason.
- Detailed queue schema, locking strategy, and database implementation are deferred to a later design stage.

## 10. LangGraph Workflow

### 10.1 States

The workflow shall include the following logical nodes:

- `FRAMEWORK_INIT`
- `EXECUTION_INIT`
- `MASTER_QUEUE_CREATOR`
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

- Select process/app configuration.
- Load the configured init module.
- Load and validate the configured Excel/CSV automation steps.
- Initialize or restart driver.
- Initialize app repository context.
- Execute configured init steps/functions when login or session setup is required.
- Prepare runtime state for processing.
- Clear any previously loaded process module so process execution can load the module for the active app/process.
- Delegate execution-cycle behavior to the execution lifecycle service.

#### MASTER_QUEUE_CREATOR

- Populate queue if enabled.
- Skip queue creation if disabled.
- Delegate queue creation behavior to the queue runtime service.

#### GET_TRANSACTION

- Fetch the next transaction.
- Lock the transaction as `IN_PROGRESS`.
- Update batch counter.
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

The framework executes the current transaction by reading the configured automation steps, resolving each step to an explicit source module and function, passing shared state into the function, and collecting a framework-readable outcome.

The process module shall be loaded at runtime by `PROCESS_TRANSACTION` for the active app/process. This prevents a module from a previous app/process execution cycle from being reused after an application switch.
Transaction execution behavior shall be delegated to the transaction runtime service.

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
else:
    mark transaction FAILED
    TRANSITION_HUB routes to GET_TRANSACTION or END based on runtime controls
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

### 10.3 Graph Routing Contract

The graph shall use `TRANSITION_HUB` as the central post-transaction decision node.

| From Node | Condition | To Node |
| --- | --- | --- |
| `FRAMEWORK_INIT` | Always | `EXECUTION_INIT` |
| `EXECUTION_INIT` | Always | `MASTER_QUEUE_CREATOR` |
| `MASTER_QUEUE_CREATOR` | Always | `GET_TRANSACTION` |
| `GET_TRANSACTION` | Transaction found | `LOGIN_APPLICATION` |
| `GET_TRANSACTION` | No transaction | `TRANSITION_HUB` |
| `LOGIN_APPLICATION` | Login already completed or login completed now | `PROCESS_TRANSACTION` |
| `PROCESS_TRANSACTION` | Always after storing result | `TRANSITION_HUB` |
| `TRANSITION_HUB` | Success/business exception and more work allowed | `GET_TRANSACTION` |
| `TRANSITION_HUB` | No transaction and wait is enabled/remaining | `GET_TRANSACTION` |
| `TRANSITION_HUB` | No transaction and no wait remains | `END` |
| `TRANSITION_HUB` | System exception and retry remains | `EXECUTION_INIT` |
| `TRANSITION_HUB` | Application switch required | `EXECUTION_INIT` |
| `TRANSITION_HUB` | Batch/end condition reached | `END` |

#### END

- Close the driver.
- Release resources.
- Complete final logging.

## 11. Runtime Control

### 11.1 `runtime_config` Fields

| Field | Purpose |
| --- | --- |
| `retry_count` | Tracks system retry attempts. |
| `batch_count` | Tracks number of processed transactions in the current batch. |
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
- **Queue** feeds transactions through a placeholder DB-backed model.
- **Runtime Modules** supply configured init and process functions.
- **Automation Steps** drive keyword-based function execution from Excel/CSV definitions.

The target outcome is a deterministic, scalable, config-driven automation framework that supports retries, batching, multi-app execution, runtime module loading, Excel/CSV-driven keyword steps, and clean separation of framework and process responsibilities.
