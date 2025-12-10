-- MySQL 초기화 스크립트

-- cron_jobs 테이블 생성
CREATE TABLE IF NOT EXISTS cron_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    cron_expression VARCHAR(100) NOT NULL,
    handler_name VARCHAR(255) NOT NULL,
    handler_params JSON,
    is_enabled TINYINT(1) DEFAULT 1,
    allow_overlap TINYINT(1) DEFAULT 1,
    max_retry INT DEFAULT 3,
    timeout_seconds INT DEFAULT 3600,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- job_executions 테이블 생성
CREATE TABLE IF NOT EXISTS job_executions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    scheduled_time TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    retry_count INT DEFAULT 0,
    error_message TEXT,
    result JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id) ON DELETE CASCADE,
    UNIQUE KEY unique_job_scheduled (job_id, scheduled_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 인덱스 생성
CREATE INDEX idx_job_executions_job_id ON job_executions(job_id);
CREATE INDEX idx_job_executions_status ON job_executions(status);
CREATE INDEX idx_job_executions_created_at ON job_executions(created_at);
CREATE INDEX idx_job_executions_scheduled_time ON job_executions(scheduled_time);
CREATE INDEX idx_cron_jobs_is_enabled ON cron_jobs(is_enabled);

-- sample_data 테이블 (샘플 핸들러용)
CREATE TABLE IF NOT EXISTS sample_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    value TEXT,
    writer_handler VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
