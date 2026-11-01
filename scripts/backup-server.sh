#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
filename="classroom-${stamp}.sqlite3"
docker compose exec -T web python manage.py backup_classroom --output "/data/backups/${filename}"
docker compose cp "web:/data/backups/${filename}" "backups/${filename}"
if docker compose exec -T web python manage.py help backup_course_files >/dev/null 2>&1; then
    archive="materials-${stamp}.tar.gz"
    docker compose exec -T web python manage.py backup_course_files --output "/data/backups/${archive}"
    docker compose cp "web:/data/backups/${archive}" "backups/${archive}"
    echo "课程资料已备份：backups/${archive}"
else
    echo '当前运行的是尚无资料库的旧版，仅备份数据库。'
fi
echo "已保存服务器备份：backups/${filename}。请再下载到另一台设备安全保存。"
