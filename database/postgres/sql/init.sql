-- PostgreSQL 초기화 스크립트

-- cron_jobs 테이블 생성
CREATE TABLE IF NOT EXISTS cron_jobs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    cron_expression VARCHAR(100) NOT NULL,
    handler_name VARCHAR(255) NOT NULL,
    handler_params JSONB,
    is_enabled BOOLEAN DEFAULT TRUE,
    allow_overlap BOOLEAN DEFAULT TRUE,
    max_retry INTEGER DEFAULT 3,
    timeout_seconds INTEGER DEFAULT 3600,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- job_executions 테이블 생성
CREATE TABLE IF NOT EXISTS job_executions (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES cron_jobs(id) ON DELETE CASCADE,
    handler_name VARCHAR(255) NOT NULL,
    scheduled_time TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    params JSONB,
    param_source VARCHAR(20) DEFAULT 'cron',
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    result JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, scheduled_time)
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_job_executions_job_id ON job_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_job_executions_handler_name ON job_executions(handler_name);
CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status);
CREATE INDEX IF NOT EXISTS idx_job_executions_param_source ON job_executions(param_source);
CREATE INDEX IF NOT EXISTS idx_job_executions_created_at ON job_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_job_executions_scheduled_time ON job_executions(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_is_enabled ON cron_jobs(is_enabled);
