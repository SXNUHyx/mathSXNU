import os
import sqlite3
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "使用SQLite在线备份API保存课堂数据库，不覆盖已有文件。"

    def add_arguments(self, parser):
        parser.add_argument("--output", default=None, help="备份文件路径，默认 .local/backups/课堂时间.sqlite3")

    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"])
        if not source.exists():
            raise CommandError("数据库不存在，请先运行 migrate。")
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S-%f")
        target = Path(options["output"] or settings.BASE_DIR / ".local" / "backups" / f"classroom-{stamp}.sqlite3")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(target, "xb", opener=lambda p, f: os.open(p, f, 0o600)):
                pass
        except FileExistsError as exc:
            raise CommandError("目标文件已存在，请换一个备份路径。") from exc
        try:
            with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
                src.backup(dst)
        except sqlite3.Error as exc:
            target.unlink(missing_ok=True)
            raise CommandError(f"备份失败：{exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"备份完成：{target}"))
