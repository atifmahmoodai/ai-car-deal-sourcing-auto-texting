#!/bin/bash
set -euo pipefail
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$APP_DB_PASSWORD" --set=ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE scout LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER DATABASE scout OWNER TO scout;
REVOKE ALL ON DATABASE scout FROM PUBLIC;
GRANT ALL ON SCHEMA public TO scout;
SQL
