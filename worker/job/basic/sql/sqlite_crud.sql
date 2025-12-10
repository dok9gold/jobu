-- sqlite_crud 핸들러용 SQLite 쿼리

-- name: insert_sample_data<!
INSERT INTO sample_data (name, value, writer_handler) VALUES (:name, :value, :writer_handler);

-- name: get_sample_data
SELECT id, name, value, writer_handler, created_at FROM sample_data ORDER BY id DESC LIMIT 10;

-- name: get_last_insert_id$
SELECT last_insert_rowid();
