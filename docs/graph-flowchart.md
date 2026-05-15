# Orqflow Graph Flowchart

```mermaid
flowchart TD
    A[framework_init<br/>load KeySteps.xlsx] --> B[execution_init]

    B -->|masterbot = true| C[master_queue_creator]
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

## Framework Initialization Notes

- `framework_init` now loads `KeySteps.xlsx` from the active project config directory before the first execution cycle starts.
- The shared Excel reader is loaded from `<share_root>/common/excel.py` using the config context resolved during startup.
- Loaded key-step data is stored on `state["key_steps"]` for later runtime nodes.
- If loading fails, framework initialization records `Outcome.SYSTEM_EXCEPTION`, stores the error in `runtime_config.last_error`, and sets `runtime_config.next_action` to `END`.
