# Orqflow Graph Flowchart

```mermaid
flowchart TD
    A[framework_init<br/>load KeySteps.xlsx] --> B[execution_init]

    B -->|masterbot = true| C[master_queue_creator<br/>load inputs and create queues]
    B -->|masterbot != true| D[get_transaction]

    C --> D

    D -->|next_action = PROCESS| E[login_application]
    D -->|no transaction| F[transition_hub]

    E -->|already logged in or login completed| I[process_transaction]
    I --> F[transition_hub]

    F -->|next_action = APP_SWITCH or RETRY| B
    F -->|next_action = GET_TRANSACTION or default| D
    F -->|next_action = END| G

    G --> H([LangGraph END])
```

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
