# Orqflow Graph Flowchart

```mermaid
flowchart TD
    A[framework_init<br/>load KeySteps.xlsx and initialize queue DB] -->|success| B[execution_init]
    A -->|initialization failure<br/>next_action = END| G[end and cleanup]

    B -->|retry preserves txn| E[login_application]
    B -->|master queue is due| C[master_queue_creator<br/>load inputs and create queues]
    B -->|eligible work exists| D[get_transaction]
    B -->|periodic masterbot not due| W[master_queue_wait]
    B -->|no work or fatal error| G
    W -->|wait_seconds elapsed<br/>MASTER_QUEUE_REFRESH| B

    C -->|queue creation completed| D
    C -->|queue creation failure<br/>next_action = END| G

    D -->|next_action = PROCESS| E[login_application]
    D -->|no transaction| F[transition_hub]

    E -->|already logged in or login completed| I[process_transaction<br/>load Module from matching KeySteps row]
    I --> F[transition_hub]

    F -->|APP_SWITCH, BATCH_COMPLETE, or RETRY| B
    F -->|next_action = GET_TRANSACTION or default| D
    F -->|system exception with no active transaction<br/>retries exhausted| G
    F -->|fatal next_action = END| G

    G -->|cleanup sets next_action = END| H([LangGraph END])
```

## Application Batch Scheduling

```mermaid
flowchart TD
    A[Fetch for active_application_id] --> B{Transaction found?}
    B -->|Yes| C[Process and finalize transaction]
    C --> D[Increment session_batch_count]
    D --> E{Positive BatchCount reached?}
    E -->|No| A
    E -->|Yes| F[EXECUTION_INIT<br/>BATCH_COMPLETE]
    B -->|No| G{Eligible transaction exists globally?}
    G -->|Yes| H[EXECUTION_INIT<br/>APP_SWITCH]
    G -->|No| F
    F --> I[Optional project reset hook]
    I --> J[Reset counter and activate next process step]
    J --> K{Work or scheduled master run remains?}
    K -->|Yes| A
    K -->|No| L[END and cleanup]
```

- `BatchCount` blank or zero means process all eligible work for that application in one session.
- A positive `BatchCount` closes/resets the application session after that many finalized transactions.
- Success, skipped business exceptions, and retry-exhausted failures count as finalized; retry attempts do not.
- With one process application, the same application is reactivated after each positive batch.
- With multiple process applications, scheduling cycles in numeric KeySteps `Sequence` order until the global eligible queue is empty.

## Master Queue Creation

```mermaid
flowchart TD
    A[Load input DataFrame] --> B[Select PROCESS_TRANSACTION KeySteps]
    B --> C[Sort by Sequence]
    C --> D[Normalize and deduplicate Application IDs]
    D --> E[Validate IDs against tbl_application]
    E --> F[Insert valid source rows into tbl_input]
    F --> G[Select matching-process inputs with blank Status]
    G --> H{Next eligible input}
    H -->|Found| I[Insert one tbl_queue row per distinct application]
    I --> J{Complete queue set succeeded?}
    J -->|Yes| K[Update input Status and QueueCreation_timestamp]
    K --> L[Commit input queue set]
    J -->|No| M[Rollback this input queue set and record failure]
    L --> H
    M --> H
    H -->|None| N[Store queue_creation_summary]
```

- `Case_Details` stores the eligible `tbl_input.ID` and `Application_Details` stores the normalized KeyStep application ID.
- Both `tbl_queue.Processing_Status` and the completed `tbl_input.Status` use `queue_config.eligible_status`, defaulting to `Queue Created`.
- The input status and timestamp are updated only after its complete distinct-application queue set succeeds.
- A failed input is rolled back independently and remains eligible for a later retry; later inputs continue processing.
- Queue creation assumes one master creator per process. Successfully updated input status prevents duplicates on normal reruns.

## Framework Initialization Notes

- `framework_init` now loads `KeySteps.xlsx` from the active project config directory before the first execution cycle starts.
- The shared Excel reader is loaded from `<share_root>/common/excel.py` using the config context resolved during startup.
- Loaded key-step data is stored on `state["key_steps"]` for later runtime nodes.
- If loading fails, framework initialization records `Outcome.SYSTEM_EXCEPTION`, stores the error in `runtime_config.last_error`, and sets `runtime_config.next_action` to `END`.
- The graph honors that `END` action immediately; failed framework initialization does not continue to `execution_init`.

## Process Transaction Notes

- The active transaction provides `queue_application_details`, which identifies its application.
- The framework selects the matching `PROCESS_TRANSACTION` row from `KeySteps.xlsx` and orders matching rows by numeric `Sequence`.
- The `Module` cell uses `package.module:function` format, for example `image_value_extraction.runtime:run_process`.
- The configured callable receives the complete shared state and returns a framework result containing `outcome`, optional `message`, optional `data`, and optional `next_action`.
- Unexpected import, configuration, execution, or result-validation failures become `Outcome.SYSTEM_EXCEPTION`.
- After retry exhaustion, a system exception without an active transaction routes to `END` instead of returning repeatedly to `GET_TRANSACTION`.
