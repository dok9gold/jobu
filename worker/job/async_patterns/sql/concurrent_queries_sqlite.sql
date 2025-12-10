-- concurrent_queries 핸들러용 SQLite 쿼리

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: get_sample_data
SELECT id, name, value, writer_handler, created_at FROM sample_data ORDER BY id DESC LIMIT 10;
