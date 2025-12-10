-- SQLite sample_data queries

-- name: insert_sample_data<!
INSERT INTO sample_data (name, value, writer_handler) VALUES (:name, :value, :writer_handler);

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;

-- name: get_all_sample_data
SELECT * FROM sample_data;

-- name: get_last_insert_id$
SELECT last_insert_rowid();

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: count_by_handler
SELECT writer_handler, COUNT(*) as cnt FROM sample_data GROUP BY writer_handler;

-- name: upsert_sample_data!
INSERT INTO sample_data (id, name, value, writer_handler) VALUES (:id, :name, :value, :writer_handler)
ON CONFLICT(id) DO UPDATE SET
    name = excluded.name,
    value = excluded.value,
    writer_handler = excluded.writer_handler;
