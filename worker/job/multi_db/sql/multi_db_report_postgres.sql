-- multi_db_report 핸들러용 PostgreSQL 쿼리

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: count_by_handler
SELECT writer_handler, COUNT(*) as cnt FROM sample_data GROUP BY writer_handler;
