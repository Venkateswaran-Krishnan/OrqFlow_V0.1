# Orqflow Requirements Review

This review is based on `Orqflow_Requirement.md`. It focuses on implementation readiness and architecture quality, without changing the requirements document itself.

## 1. Remaining Gaps Before Production Implementation

These items should be resolved before production hardening, because they directly affect module boundaries, state shape, and node behavior.

1. **Automation step and function contracts are partially defined**
   - The requirements now define the implemented CSV columns: `order`, `phase`, `keyword`, `source`, `function_name`, `parameters`, and `on_error`.
   - The requirements now define the implemented `StepResult` shape and allowed outcome family.
   - Remaining detail: define production behavior for `on_error`, parameter validation, app/transaction filtering, and missing/invalid parameter payloads.

2. **LangGraph node result contract is now partially defined**
   - The requirements now state that `PROCESS_TRANSACTION` stores the execution outcome and always routes to `TRANSITION_HUB`.
   - `TRANSITION_HUB` is the central post-transaction decision node for success, business exception, system exception retry, app switch, batch completion, and end.
   - The allowed `runtime_config.next_action` values are now documented.
   - Remaining implementation detail: define strict ownership for each runtime field and validate unknown `next_action` values.

3. **Service ownership rules need more precision**
   - The implementation now uses thin LangGraph nodes and delegates behavior to services.
   - Remaining detail: define which service owns each state field, especially `retry_count`, `batch_count`, `wait_count`, `txn`, `last_status`, `last_error`, and `next_action`.

4. **Execution initialization reset rules are not fully defined**
   - The split between framework initialization and execution initialization is clear.
   - Implementation still needs exact reset behavior for retry, batch, wait, transaction, app switch, and login/session state.
   - This is a blocker because recovery behavior depends on what survives a retry.

5. **Exception classification needs a framework-level contract**
   - The requirements distinguish business exceptions from system exceptions.
   - Implementation needs a common exception/result model so step functions classify failures consistently.
   - Without this, retries may be triggered for business failures or skipped for true system failures.

## 2. Architecture Risks

These risks do not invalidate the design, but they should be controlled during implementation.

1. **Mutable shared state can become hard to reason about**
   - A single shared state object is appropriate for LangGraph orchestration.
   - Risk: too many services may mutate state directly.
   - Mitigation: continue moving shared state mutations into `runtime_state` helpers and define service ownership tables.

2. **Execution initialization may accidentally become full initialization**
   - Recovery should restart driver/session/process context, not reload the entire framework.
   - Risk: retry paths may reinitialize logging, queue adapter, config, or global services.
   - Mitigation: keep framework services outside execution-cycle reset logic.

3. **Runtime module loading can couple process code to framework internals**
   - Runtime loading is powerful and fits the framework goal.
   - The current implementation now lazy-loads the process module in `PROCESS_TRANSACTION` and invalidates it during execution reinitialization.
   - Risk: init/process functions may reach into internal framework objects instead of using stable APIs.
   - Mitigation: expose a narrow framework context or service facade.

4. **Driver lifecycle and login lifecycle may blur together**
   - Restarting the driver may require login, but login is app/process-specific.
   - Risk: browser restart logic may become tangled with init module login/session functions.
   - Mitigation: let the framework own driver restart and let configured init steps own app login/setup.

5. **Queue schema baseline is captured but incomplete**
   - The visible production `rpa_prod` schema is now documented in the requirements.
   - Risk: the pasted dump was truncated around `tbl_process` and `tbl_queue`, and full definitions for `tbl_application`, `tbl_login`, `tbl_login_process_link`, and `tbl_output` were not visible.
   - Mitigation: keep the queue adapter interface explicit and capture a clean full schema dump before writing production SQL, locking, leasing, retries, and app-switch behavior.

6. **Retry semantics can conflict with transaction status**
   - System exception retry routes to execution initialization.
   - Risk: a transaction may remain `IN_PROGRESS` across retries without clear ownership or timeout behavior.
   - Mitigation: document whether retry keeps the same transaction locked, refreshes the lock, or releases/reacquires it later.

## 3. Missing Contracts / Interfaces

The following contracts should be added before or during early implementation design.

| Contract | Needed Decisions |
| --- | --- |
| Runtime modules | Missing module handling, reload policy for app switch, cleanup behavior, allowed function signatures beyond `state, **params`. |
| Automation steps | `on_error` behavior, parameter schema validation, filtering by transaction/app. |
| Step/function result | Exact behavior for `next_action`, retry hints, and transaction update payloads. |
| Driver wrapper | Start, stop, restart, page access, context access, screenshot/trace hooks, cleanup guarantees. |
| Object repository | JSON schema, locator fields, fallback rules, cache key, cache invalidation, missing locator behavior. |
| Config schema | Required sections, validation rules, defaults, process/app selection, driver module path. |
| Runtime state | Service ownership by field, reset rules, validation of allowed status and action values. |
| LangGraph node result | Unknown action handling, app-switch config update contract, error propagation rules. |
| Queue adapter | Fetch, lock, mark success, mark skipped, mark failed, no-transaction result, placeholder transaction shape. |
| Logging events | Required event names, transition log shape, transaction lifecycle logs, error logs. |

## 4. Suggested Requirement Refinements

These refinements would make the requirements more testable and easier to implement.

1. **Clarify automation step schema**
   - Current intent: Excel/CSV-driven keyword steps with explicit module/function mapping.
   - Suggested refinement: define required columns for order, keyword, source module, function name, parameters, and failure handling.

2. **Define state as a typed contract**
   - Current intent: one shared state object.
   - Suggested refinement: replace broad `Any` state entries with typed runtime/service contracts as the framework stabilizes.

3. **Make execution initialization reset behavior explicit**
   - Current intent: execution initialization can rerun during retry, app switch, and recovery.
   - Suggested refinement: list which runtime fields are preserved and which are reset for each trigger.

4. **Separate driver restart from app login**
   - Current intent: driver restarts during system exception and app switch.
   - Suggested refinement: framework restarts browser; configured init steps perform app-specific login/session setup.

5. **Define the DB-backed queue adapter boundary**
   - Current intent: the production schema baseline is documented, but exact SQL behavior is pending.
   - Suggested refinement: define the queue adapter methods now using `tbl_queue` and `tbl_input` as the transaction source, while postponing exact locking/isolation SQL until the full schema is available.

6. **Make non-functional requirements measurable**
   - Current language includes reliability, performance, maintainability, and observability goals.
   - Suggested refinement: turn each into acceptance checks such as no per-transaction browser recreation, required transition logs, and no hardcoded locators.

7. **Document service ownership**
   - Current implementation has service modules for framework lifecycle, execution lifecycle, queue runtime, transaction runtime, transition runtime, cleanup, and runtime state helpers.
   - Suggested refinement: add a state ownership matrix mapping each state field to the service allowed to write it.

## 5. Open Questions For You

These are the remaining design decisions that are not fully answered by the current requirements.

1. What exact Excel/CSV columns are required for automation steps, and which columns are optional?

2. What exact object should each executed step return: a simple status enum, or a structured result with status, error, output data, and routing hint?

3. During a system exception retry, should the same transaction remain locked as `IN_PROGRESS`, or should the framework release and reacquire it?

4. Should login/session setup be represented as required init steps, optional init steps, or process/app-config-driven steps?

5. Should `repo` and `driver` be exposed directly through state to init/process functions, or wrapped in a narrower process context object?

6. What should happen when an object repository locator is missing or both primary and fallback locators fail?

7. Should application switching be driven by queue transaction data, process config, or an explicit transition decision from step execution?

8. What is the minimum logging payload required for every state transition beyond the current event name and debug values?

9. Should retry count be per transaction, per execution cycle, or both?

10. Should batch and wait counters reset on app switch, system retry, both, or only when a new execution cycle starts?

## 6. Review Summary

The requirements are strong enough to describe the intended framework direction. The main work before implementation is to formalize the contracts that connect the architecture:

- automation step schema, runtime module loading, and result model
- typed shared state and service mutation ownership
- execution initialization reset behavior
- exception classification and retry semantics
- driver/repository/config/queue adapter interfaces
- app-switch process config update contract

The queue should now be treated as a DB-backed adapter design task. The documented schema baseline should guide the contract, and a clean full dump is still required before implementation.
