-- name: tbl_input_columns
PRAGMA table_info(tbl_input);

-- name: insert_tbl_input
INSERT INTO tbl_input ({columns})
VALUES ({placeholders});

-- name: select_application_ids
SELECT ID
FROM tbl_application;

-- name: select_inputs_for_queue_creation
SELECT ID
FROM tbl_input
WHERE Process = ?
  AND (Status IS NULL OR TRIM(Status) = '')
ORDER BY ID;

-- name: insert_tbl_queue
INSERT INTO tbl_queue (
    Case_Details,
    Application_Details,
    Processing_Status
)
VALUES (?, ?, ?);

-- name: mark_input_queue_created
UPDATE tbl_input
SET Status = ?,
    QueueCreation_timestamp = CURRENT_TIMESTAMP
WHERE ID = ?
  AND Process = ?
  AND (Status IS NULL OR TRIM(Status) = '');

-- name: fetch_next_transaction
SELECT
    q.ID AS queue_id,
    q.Case_Details AS queue_case_details,
    q.Application_Details AS queue_application_details,
    q.Bot_Name AS queue_bot_name,
    q.Processing_Status AS queue_processing_status,
    q.CTO_Details AS queue_cto_details,
    q.Evidence_Status AS queue_evidence_status,
    q.Output_tbl_Status AS queue_output_tbl_status,
    q.Bot_Comment AS queue_bot_comment,
    q.Dependency AS queue_dependency,
    q.ProcessingSTART_timestamp AS queue_processing_start_timestamp,
    q.ProcessingEND_timestamp AS queue_processing_end_timestamp,
    i.ID AS input_id,
    i.Processor AS input_processor,
    i.Process AS input_process,
    i.Case_Number AS input_case_number,
    i.Transaction_ID AS input_transaction_id,
    i.Case_Status AS input_case_status,
    i.Chargeback_Date AS input_chargeback_date,
    i.Case_Json AS input_case_json,
    i.Transaction_Amount AS input_transaction_amount,
    i.Mid_Alias AS input_mid_alias,
    i.MID_Number AS input_mid_number,
    i.Case_ID AS input_case_id,
    i.Chargeback_Amount AS input_chargeback_amount,
    i.Transaction_Date AS input_transaction_date,
    i.Deadline_Date AS input_deadline_date,
    i.Card_First_Six AS input_card_first_six,
    i.Card_Last_Four AS input_card_last_four,
    i.Card_Type AS input_card_type,
    i.Status AS input_status,
    i.QueueCreation_timestamp AS input_queue_creation_timestamp,
    i.Input_Identifier AS input_identifier,
    i.Institution AS input_institution,
    i.BUnit AS input_bunit
FROM tbl_queue q
JOIN tbl_input i ON i.ID = q.Case_Details
WHERE q.Processing_Status IN (?, ?)
  AND q.Application_Details = ?
ORDER BY
    CASE
        WHEN q.Processing_Status = ? THEN 0
        ELSE 1
    END,
    q.ID
LIMIT 1;

-- name: fetch_any_eligible_transaction
SELECT ID
FROM tbl_queue
WHERE Processing_Status IN (?, ?)
ORDER BY ID
LIMIT 1;

-- name: mark_transaction_in_progress
UPDATE tbl_queue
SET Processing_Status = ?,
    Bot_Name = ?,
    ProcessingSTART_timestamp = CURRENT_TIMESTAMP
WHERE ID = ?;

-- name: mark_transaction_success
UPDATE tbl_queue
SET Processing_Status = ?,
    Bot_Comment = CASE
        WHEN ? IS NULL OR ? = '' THEN Bot_Comment
        WHEN Bot_Comment IS NULL OR Bot_Comment = '' THEN ?
        ELSE Bot_Comment || char(10) || ?
    END,
    CTO_Details = CASE
        WHEN ? IS NULL OR ? = '' THEN CTO_Details
        ELSE ?
    END,
    ProcessingEND_timestamp = CURRENT_TIMESTAMP
WHERE ID = ?;

-- name: mark_transaction_skipped
UPDATE tbl_queue
SET Processing_Status = ?,
    Bot_Comment = CASE
        WHEN ? IS NULL OR ? = '' THEN Bot_Comment
        WHEN Bot_Comment IS NULL OR Bot_Comment = '' THEN ?
        ELSE Bot_Comment || char(10) || ?
    END,
    CTO_Details = CASE
        WHEN ? IS NULL OR ? = '' THEN CTO_Details
        ELSE ?
    END,
    ProcessingEND_timestamp = CURRENT_TIMESTAMP
WHERE ID = ?;

-- name: mark_transaction_failed
UPDATE tbl_queue
SET Processing_Status = ?,
    Bot_Comment = CASE
        WHEN ? IS NULL OR ? = '' THEN Bot_Comment
        WHEN Bot_Comment IS NULL OR Bot_Comment = '' THEN ?
        ELSE Bot_Comment || char(10) || ?
    END,
    CTO_Details = CASE
        WHEN ? IS NULL OR ? = '' THEN CTO_Details
        ELSE ?
    END,
    ProcessingEND_timestamp = CURRENT_TIMESTAMP
WHERE ID = ?;
