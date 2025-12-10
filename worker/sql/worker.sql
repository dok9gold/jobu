-- name: get_pending_executions
-- PENDING 상태의 잡 목록 조회 (LIMIT 적용)
SELECT
    e.id,
    e.job_id,
    e.scheduled_time,
    e.retry_count,
    e.created_at,
    j.name as job_name,
    j.handler_name,
    j.handler_params,
    j.max_retry,
    j.timeout_seconds
FROM job_executions e
JOIN cron_jobs j ON e.job_id = j.id
WHERE e.status = 'PENDING'
ORDER BY e.created_at ASC
LIMIT :limit;

-- name: claim_execution!
-- PENDING -> RUNNING 원자적 변경 (잡 선점)
UPDATE job_executions
SET
    status = 'RUNNING',
    started_at = CURRENT_TIMESTAMP
WHERE id = :execution_id AND status = 'PENDING';

-- name: complete_execution!
-- 실행 완료 (성공)
UPDATE job_executions
SET
    status = 'SUCCESS',
    finished_at = CURRENT_TIMESTAMP,
    result = :result
WHERE id = :execution_id;

-- name: fail_execution!
-- 실행 실패
UPDATE job_executions
SET
    status = 'FAILED',
    finished_at = CURRENT_TIMESTAMP,
    error_message = :error_message,
    retry_count = retry_count + 1
WHERE id = :execution_id;

-- name: timeout_execution!
-- 실행 타임아웃
UPDATE job_executions
SET
    status = 'TIMEOUT',
    finished_at = CURRENT_TIMESTAMP,
    error_message = 'Execution timed out',
    retry_count = retry_count + 1
WHERE id = :execution_id;

-- name: reset_to_pending!
-- 재시도를 위해 PENDING으로 복귀 (error_message는 이력으로 유지)
UPDATE job_executions
SET
    status = 'PENDING',
    started_at = NULL,
    finished_at = NULL
WHERE id = :execution_id;

-- name: get_execution_by_id^
-- ID로 실행 정보 조회
SELECT
    e.id,
    e.job_id,
    e.scheduled_time,
    e.status,
    e.started_at,
    e.finished_at,
    e.retry_count,
    e.error_message,
    e.result,
    e.created_at,
    j.handler_name,
    j.handler_params,
    j.max_retry,
    j.timeout_seconds
FROM job_executions e
JOIN cron_jobs j ON e.job_id = j.id
WHERE e.id = :execution_id;
