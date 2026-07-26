-- name: tbl_input_columns
SHOW COLUMNS FROM tbl_input;

-- name: insert_tbl_input
INSERT INTO tbl_input ({columns})
VALUES ({placeholders});

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
WHERE q.Processing_Status = %s
ORDER BY q.ID
LIMIT 1;

-- name: mark_transaction_in_progress
UPDATE tbl_queue
SET Processing_Status = %s,
    Bot_Name = %s,
    ProcessingSTART_timestamp = CURRENT_TIMESTAMP
WHERE ID = %s;

-- name: mark_transaction_success
UPDATE tbl_queue
SET Processing_Status = %s,
    Bot_Comment = CASE
        WHEN %s IS NULL OR %s = '' THEN Bot_Comment
        WHEN Bot_Comment IS NULL OR Bot_Comment = '' THEN %s
        ELSE CONCAT(Bot_Comment, CHAR(10), %s)
    END,
    ProcessingEND_timestamp = CURRENT_TIMESTAMP
WHERE ID = %s;

-- name: mark_transaction_skipped
UPDATE tbl_queue
SET Processing_Status = %s,
    Bot_Comment = CASE
        WHEN %s IS NULL OR %s = '' THEN Bot_Comment
        WHEN Bot_Comment IS NULL OR Bot_Comment = '' THEN %s
        ELSE CONCAT(Bot_Comment, CHAR(10), %s)
    END,
    ProcessingEND_timestamp = CURRENT_TIMESTAMP
WHERE ID = %s;

-- name: mark_transaction_failed
UPDATE tbl_queue
SET Processing_Status = %s,
    Bot_Comment = CASE
        WHEN %s IS NULL OR %s = '' THEN Bot_Comment
        WHEN Bot_Comment IS NULL OR Bot_Comment = '' THEN %s
        ELSE CONCAT(Bot_Comment, CHAR(10), %s)
    END,
    ProcessingEND_timestamp = CURRENT_TIMESTAMP
WHERE ID = %s;
