#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
filename="classroom-${stamp}.sqlite3"
docker compose exec -T web python manage.py backup_classroom --output "/data/backups/${filename}"
docker compose cp "web:/data/backups/${filename}" "backups/${filename}"
echo "已保存服务器备份：backups/${filename}。请再下载到另一台设备安全保存。"
