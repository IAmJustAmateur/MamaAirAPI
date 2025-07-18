#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -o errexit
set -o pipefail
set -o nounset

# Function to wait for PostgreSQL to be ready
wait_for_postgres() {
  echo "Waiting for PostgreSQL..."
  until PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c '\q' > /dev/null 2>&1; do
    sleep 1
  done
  echo "PostgreSQL is available"
}

# Check if DJANGO_ENV is set to production
if [ "$DJANGO_ENV" = "production" ]; then
  wait_for_postgres
  echo "Applying database migrations..."
  python manage.py migrate --noinput

  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

echo "Starting Uvicorn server..."
exec uvicorn agent_api.asgi:application --host 0.0.0.0 --port 8000 --proxy-headers
