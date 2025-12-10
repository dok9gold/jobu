-- mysql_crud 핸들러용 MySQL 쿼리

-- name: insert_sample_data!
INSERT INTO sample_data (name, value, writer_handler) VALUES (:name, :value, :writer_handler);

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;

-- name: get_last_insert_id$
SELECT LAST_INSERT_ID();
