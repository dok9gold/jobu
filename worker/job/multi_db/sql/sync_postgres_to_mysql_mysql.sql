-- sync_postgres_to_mysql 핸들러용 MySQL 쿼리

-- name: upsert_sample_data!
INSERT INTO sample_data (id, name, value, writer_handler)
VALUES (:id, :name, :value, :writer_handler)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    value = VALUES(value),
    writer_handler = VALUES(writer_handler);
