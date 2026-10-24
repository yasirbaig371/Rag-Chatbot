-- Create role rag_user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rag_user') THEN
        CREATE ROLE rag_user WITH LOGIN PASSWORD 'rag_password' CREATEDB;
    END IF;
END
$$;

-- Create rag_db
SELECT 'CREATE DATABASE rag_db OWNER rag_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'rag_db')\gexec

-- Create rag_test_db for Pytest isolation
SELECT 'CREATE DATABASE rag_test_db OWNER rag_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'rag_test_db')\gexec

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE rag_db TO rag_user;
GRANT ALL PRIVILEGES ON DATABASE rag_test_db TO rag_user;
