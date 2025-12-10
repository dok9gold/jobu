-- Admin API용 SQL 쿼리

-- ============================================
-- CRON 관련 쿼리
-- ============================================

-- name: get_all_crons
-- 모든 크론 조회
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
ORDER BY id;

-- name: get_crons_paged
-- 크론 목록 조회 (페이징)
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
ORDER BY id DESC
LIMIT :limit OFFSET :offset;

-- name: get_crons_by_enabled
-- 활성화 상태로 크론 목록 조회 (페이징)
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE is_enabled = :is_enabled
ORDER BY id DESC
LIMIT :limit OFFSET :offset;

-- name: count_crons^
-- 전체 크론 수
SELECT COUNT(*) as cnt FROM cron_jobs;

-- name: count_crons_by_enabled^
-- 활성화 상태별 크론 수
SELECT COUNT(*) as cnt FROM cron_jobs WHERE is_enabled = :is_enabled;

-- name: get_cron_by_id^
-- ID로 크론 조회
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE id = :cron_id;

-- name: get_cron_by_name^
-- 이름으로 크론 조회
SELECT
    id, name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds, created_at, updated_at
FROM cron_jobs
WHERE name = :name;

-- name: insert_cron<!
-- 크론 생성
INSERT INTO cron_jobs (
    name, description, cron_expression,
    handler_name, handler_params, is_enabled, allow_overlap,
    max_retry, timeout_seconds
) VALUES (
    :name, :description, :cron_expression,
    :handler_name, :handler_params, :is_enabled, :allow_overlap,
    :max_retry, :timeout_seconds
);

-- name: update_cron!
-- 크론 수정
UPDATE cron_jobs
SET
    name = :name,
    description = :description,
    cron_expression = :cron_expression,
    handler_name = :handler_name,
    handler_params = :handler_params,
    is_enabled = :is_enabled,
    allow_overlap = :allow_overlap,
    max_retry = :max_retry,
    timeout_seconds = :timeout_seconds,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :cron_id;

-- name: toggle_cron!
-- 크론 활성화/비활성화 토글
UPDATE cron_jobs
SET
    is_enabled = :is_enabled,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :cron_id;

-- name: delete_cron!
-- 크론 삭제
DELETE FROM cron_jobs WHERE id = :cron_id;

-- ============================================
-- JOB 실행 이력 관련 쿼리
-- ============================================

-- name: get_jobs_paged
-- 잡 실행 이력 목록 조회 (페이징, 크론 이름 포함)
SELECT
    e.id, e.job_id, c.name as cron_name, e.scheduled_time, e.status,
    e.started_at, e.finished_at, e.retry_count,
    e.error_message, e.result, e.created_at
FROM job_executions e
LEFT JOIN cron_jobs c ON e.job_id = c.id
ORDER BY e.id DESC
LIMIT :limit OFFSET :offset;

-- name: get_jobs_by_cron
-- 특정 크론의 잡 실행 이력 조회 (페이징)
SELECT
    e.id, e.job_id, c.name as cron_name, e.scheduled_time, e.status,
    e.started_at, e.finished_at, e.retry_count,
    e.error_message, e.result, e.created_at
FROM job_executions e
LEFT JOIN cron_jobs c ON e.job_id = c.id
WHERE e.job_id = :cron_id
ORDER BY e.id DESC
LIMIT :limit OFFSET :offset;

-- name: get_jobs_by_status
-- 상태별 잡 실행 이력 조회 (페이징)
SELECT
    e.id, e.job_id, c.name as cron_name, e.scheduled_time, e.status,
    e.started_at, e.finished_at, e.retry_count,
    e.error_message, e.result, e.created_at
FROM job_executions e
LEFT JOIN cron_jobs c ON e.job_id = c.id
WHERE e.status = :status
ORDER BY e.id DESC
LIMIT :limit OFFSET :offset;

-- name: get_jobs_by_cron_and_status
-- 크론 및 상태별 잡 실행 이력 조회 (페이징)
SELECT
    e.id, e.job_id, c.name as cron_name, e.scheduled_time, e.status,
    e.started_at, e.finished_at, e.retry_count,
    e.error_message, e.result, e.created_at
FROM job_executions e
LEFT JOIN cron_jobs c ON e.job_id = c.id
WHERE e.job_id = :cron_id AND e.status = :status
ORDER BY e.id DESC
LIMIT :limit OFFSET :offset;

-- name: count_jobs^
-- 전체 잡 실행 이력 수
SELECT COUNT(*) as cnt FROM job_executions;

-- name: count_jobs_by_cron^
-- 특정 크론의 잡 실행 이력 수
SELECT COUNT(*) as cnt FROM job_executions WHERE job_id = :cron_id;

-- name: count_jobs_by_status^
-- 상태별 잡 실행 이력 수
SELECT COUNT(*) as cnt FROM job_executions WHERE status = :status;

-- name: count_jobs_by_cron_and_status^
-- 크론 및 상태별 잡 실행 이력 수
SELECT COUNT(*) as cnt FROM job_executions WHERE job_id = :cron_id AND status = :status;

-- name: get_job_by_id^
-- ID로 잡 실행 이력 조회
SELECT
    e.id, e.job_id, c.name as cron_name, e.scheduled_time, e.status,
    e.started_at, e.finished_at, e.retry_count,
    e.error_message, e.result, e.created_at
FROM job_executions e
LEFT JOIN cron_jobs c ON e.job_id = c.id
WHERE e.id = :execution_id;

-- name: retry_job!
-- 잡 재시도 (상태를 PENDING으로 변경)
UPDATE job_executions
SET
    status = 'PENDING',
    started_at = NULL,
    finished_at = NULL,
    error_message = NULL,
    result = NULL
WHERE id = :execution_id;

-- name: delete_job!
-- 잡 실행 이력 삭제
DELETE FROM job_executions WHERE id = :execution_id;
