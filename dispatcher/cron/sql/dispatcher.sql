-- name: get_all_jobs
-- 모든 CRON 작업 조회
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
ORDER BY id;

-- name: get_enabled_jobs
-- 활성화된 CRON 작업만 조회
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE is_enabled = TRUE
ORDER BY id;

-- name: get_job_by_id^
-- ID로 작업 조회 (단일 결과)
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE id = :job_id;

-- name: get_job_by_name^
-- 이름으로 작업 조회
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE name = :name;

-- name: insert_job<!
-- 새 작업 등록
INSERT INTO cron_jobs (
    name, description, cron_expression,
    handler_name, handler_params, is_enabled,
    max_retry, timeout_seconds
) VALUES (
    :name, :description, :cron_expression,
    :handler_name, :handler_params, :is_enabled,
    :max_retry, :timeout_seconds
);

-- name: update_job!
-- 작업 수정
UPDATE cron_jobs
SET
    name = :name,
    description = :description,
    cron_expression = :cron_expression,
    handler_name = :handler_name,
    handler_params = :handler_params,
    is_enabled = :is_enabled,
    max_retry = :max_retry,
    timeout_seconds = :timeout_seconds,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :job_id;

-- name: toggle_job_status!
-- 작업 활성화/비활성화 토글
UPDATE cron_jobs
SET
    is_enabled = :is_enabled,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :job_id;

-- name: delete_job!
-- 작업 삭제
DELETE FROM cron_jobs WHERE id = :job_id;

-- name: get_executions_by_job_id
-- 특정 작업의 실행 이력 조회
SELECT
    id, job_id, status, started_at, finished_at,
    retry_count, error_message, result, created_at
FROM job_executions
WHERE job_id = :job_id
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset;

-- name: get_recent_executions
-- 최근 실행 이력 조회
SELECT
    e.id, e.job_id, j.name as job_name, e.status,
    e.started_at, e.finished_at, e.retry_count,
    e.error_message, e.result, e.created_at
FROM job_executions e
JOIN cron_jobs j ON e.job_id = j.id
ORDER BY e.created_at DESC
LIMIT :limit;

-- name: get_execution_by_id^
-- ID로 실행 이력 조회
SELECT
    id, job_id, status, started_at, finished_at,
    retry_count, error_message, result, created_at
FROM job_executions
WHERE id = :execution_id;

-- name: get_pending_executions
-- 대기 중인 실행 조회
SELECT
    e.id, e.job_id, j.name as job_name, j.handler_name,
    j.handler_params, j.max_retry, j.timeout_seconds,
    e.retry_count, e.created_at
FROM job_executions e
JOIN cron_jobs j ON e.job_id = j.id
WHERE e.status = 'PENDING'
ORDER BY e.created_at ASC;

-- name: insert_execution<!
-- 새 실행 이력 생성 (scheduled_time 포함)
INSERT INTO job_executions (job_id, handler_name, scheduled_time, params, param_source, status)
VALUES (:job_id, :handler_name, :scheduled_time, :params, 'cron', 'PENDING');

-- name: create_execution_if_not_exists$
-- 중복 방지 Job 생성 (ON CONFLICT DO NOTHING)
-- 동일한 job_id + scheduled_time 조합이 이미 존재하면 무시
INSERT INTO job_executions (job_id, handler_name, scheduled_time, params, param_source, status)
VALUES (:job_id, :handler_name, :scheduled_time, :params, 'cron', 'PENDING')
ON CONFLICT(job_id, scheduled_time) DO NOTHING;

-- name: check_execution_exists^
-- 동일 job_id + scheduled_time 조합 존재 확인
SELECT id
FROM job_executions
WHERE job_id = :job_id AND scheduled_time = :scheduled_time;

-- name: has_incomplete_execution^
-- 미완료(PENDING, RUNNING) 상태의 실행 존재 확인
-- allow_overlap=0인 크론에서 사용
SELECT id
FROM job_executions
WHERE job_id = :job_id AND status IN ('PENDING', 'RUNNING')
LIMIT 1;

-- name: start_execution!
-- 실행 시작
UPDATE job_executions
SET
    status = 'RUNNING',
    started_at = CURRENT_TIMESTAMP
WHERE id = :execution_id;

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
    error_message = 'Execution timed out'
WHERE id = :execution_id;

-- name: get_execution_stats^
-- 실행 통계 조회
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
    SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) as running_count,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending_count
FROM job_executions
WHERE created_at >= :since;

-- name: cleanup_old_executions!
-- 오래된 실행 이력 정리
DELETE FROM job_executions
WHERE created_at < :before_date
AND status IN ('SUCCESS', 'FAILED', 'TIMEOUT');
