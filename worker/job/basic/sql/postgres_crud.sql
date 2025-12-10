-- postgres_crud 핸들러용 PostgreSQL 쿼리

-- name: insert_sample_data_returning^
INSERT INTO sample_data (name, value, writer_handler)
VALUES (:name, :value, :writer_handler) RETURNING id;

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;
