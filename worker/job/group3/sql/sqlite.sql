-- SQLite sample_data queries for group3

-- name: insert_sample_data<!
INSERT INTO sample_data (name, value, writer_handler) VALUES (:name, :value, :writer_handler);

-- name: get_sample_data
SELECT id, name, value, writer_handler, created_at FROM sample_data ORDER BY id DESC LIMIT 10;

-- name: get_all_sample_data
SELECT * FROM sample_data;

-- name: get_last_insert_id$
SELECT last_insert_rowid();

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: get_sample_by_id^
SELECT * FROM sample_data WHERE id = :id;

-- name: update_sample_data!
UPDATE sample_data SET name = :name, value = :value WHERE id = :id;

-- name: delete_sample_data!
DELETE FROM sample_data WHERE id = :id;
