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
    job_id INTEGER NOT NULL REFERENCES cron_jobs(id) ON DELETE CASCADE,
    scheduled_time TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    result JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, scheduled_time)
);

-- sample_data 테이블 생성 (샘플 핸들러용)
CREATE TABLE IF NOT EXISTS sample_data (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    value TEXT,
    writer_handler VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_job_executions_job_id ON job_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status);
CREATE INDEX IF NOT EXISTS idx_job_executions_created_at ON job_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_job_executions_scheduled_time ON job_executions(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_is_enabled ON cron_jobs(is_enabled);
CREATE INDEX IF NOT EXISTS idx_sample_data_writer_handler ON sample_data(writer_handler);
