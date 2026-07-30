#!/bin/sh
set -eu

database_exists="$(
  psql \
    --host postgres \
    --username "${POSTGRES_USER}" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command "SELECT 1 FROM pg_database WHERE datname = '${KEYCLOAK_DB}'"
)"

if [ "${database_exists}" != "1" ]; then
  createdb \
    --host postgres \
    --username "${POSTGRES_USER}" \
    "${KEYCLOAK_DB}"
fi

echo "PostgreSQL application and Keycloak databases are ready."
