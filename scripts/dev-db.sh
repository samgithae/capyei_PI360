#!/bin/sh
# Local dev database (PostgreSQL in Docker, small and persistent).
#   scripts/dev-db.sh up        start it (waits until ready)
#   scripts/dev-db.sh down      stop it (data is kept)
#   scripts/dev-db.sh url       print the DATABASE_URL for the API (contains the password: do not paste it anywhere)
#   scripts/dev-db.sh backup    dump to ~/pi360-backups/ (outside the repo)
#   scripts/dev-db.sh restore FILE
# Synthetic data only (SEC-14).
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
compose() { docker compose --env-file "$ROOT/.env" -f "$ROOT/docker-compose.dev-db.yml" -p pi360-dev "$@"; }
BACKUPS="$HOME/pi360-backups"

pw() { grep '^POSTGRES_PASSWORD=' "$ROOT/.env" | cut -d= -f2-; }

case "${1:-}" in
  up)
    compose up -d --wait
    echo "Dev database is up on 127.0.0.1:5433"
    ;;
  down)
    compose down
    echo "Stopped. Data is kept in the pi360_devdata volume."
    ;;
  url)
    echo "postgres://pi360:$(pw)@127.0.0.1:5433/pi360_dev"
    ;;
  backup)
    mkdir -p "$BACKUPS"
    FILE="$BACKUPS/pi360-dev-$(date +%Y%m%d-%H%M%S).sql.gz"
    compose exec -T db pg_dump -U pi360 pi360_dev | gzip > "$FILE"
    echo "Saved $FILE"
    ls -1t "$BACKUPS"/pi360-dev-*.sql.gz | tail -n +11 | xargs -I{} rm -f {}  # keep the newest 10
    ;;
  restore)
    FILE="${2:?usage: dev-db.sh restore FILE}"
    compose exec -T db psql -U pi360 -d postgres -c "DROP DATABASE IF EXISTS pi360_dev" -c "CREATE DATABASE pi360_dev"
    gunzip -c "$FILE" | compose exec -T db psql -U pi360 -d pi360_dev -q
    echo "Restored $FILE"
    ;;
  *)
    echo "usage: dev-db.sh up|down|url|backup|restore FILE" >&2
    exit 2
    ;;
esac
