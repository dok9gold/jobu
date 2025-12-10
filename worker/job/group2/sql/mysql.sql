-- MySQL sample_data queries

-- name: insert_sample_data!
INSERT INTO sample_data (name, value, writer_handler) VALUES (:name, :value, :writer_handler);

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;

-- name: get_all_sample_data
SELECT * FROM sample_data;

-- name: get_last_insert_id$
SELECT LAST_INSERT_ID();

-- name: upsert_sample_data!
INSERT INTO sample_data (id, name, value, writer_handler)
VALUES (:id, :name, :value, :writer_handler)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    value = VALUES(value),
    writer_handler = VALUES(writer_handler);

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: count_by_handler
SELECT writer_handler, COUNT(*) as cnt FROM sample_data GROUP BY writer_handler;
