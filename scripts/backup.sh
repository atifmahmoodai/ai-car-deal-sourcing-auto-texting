#!/bin/bash
set -euo pipefail
umask 077
mkdir -p backups
name="backups/scout-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U scout -Fc scout > "$name"
sha256sum "$name" > "$name.sha256"
echo "Created $name. Encrypt, copy off-host and verify a restore."
