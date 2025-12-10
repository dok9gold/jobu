-- sync_sqlite_to_postgres 핸들러용 PostgreSQL 쿼리

-- name: upsert_sample_data!
INSERT INTO sample_data (id, name, value, writer_handler)
VALUES (:id, :name, :value, :writer_handler)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    value = EXCLUDED.value,
    writer_handler = EXCLUDED.writer_handler;
