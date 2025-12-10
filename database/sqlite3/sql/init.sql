-- name: create_cron_jobs_table#
-- cron_jobs 테이블 생성
CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    cron_expression TEXT NOT NULL,
    handler_name TEXT NOT NULL,
    handler_params TEXT,
    is_enabled INTEGER DEFAULT 1,
    allow_overlap INTEGER DEFAULT 1,
    max_retry INTEGER DEFAULT 3,
    timeout_seconds INTEGER DEFAULT 3600,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- name: create_job_executions_table#
-- job_executions 테이블 생성
CREATE TABLE IF NOT EXISTS job_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    scheduled_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TEXT,
    finished_at TEXT,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id) ON DELETE CASCADE,
    UNIQUE(job_id, scheduled_time)
);

-- name: create_indexes#
-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_job_executions_job_id ON job_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status);
CREATE INDEX IF NOT EXISTS idx_job_executions_created_at ON job_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_job_executions_scheduled_time ON job_executions(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_is_enabled ON cron_jobs(is_enabled);

