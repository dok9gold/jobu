-- name: get_job_by_handler_name^
-- handler_name으로 cron_job 조회 (base params 가져오기 위함)
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE handler_name = :handler_name
LIMIT 1;

-- name: create_event_execution$
-- 이벤트 기반 실행 레코드 생성
INSERT INTO job_executions (
    job_id, handler_name, scheduled_time, params, param_source, status
) VALUES (
    :job_id, :handler_name, :scheduled_time, :params, 'event', 'PENDING'
)
RETURNING id;

-- name: get_execution_by_id^
-- ID로 실행 정보 조회
SELECT
    id, job_id, handler_name, scheduled_time, status,
    params, param_source, started_at, finished_at,
    retry_count, error_message, result, created_at
FROM job_executions
WHERE id = :execution_id;
