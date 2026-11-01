import os
from pathlib import Path
import tarfile
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "备份私有课程文件，不包含.env或数据库密钥；跳过符号链接。"

    def add_arguments(self, parser):
        parser.add_argument("--output", default=None)

    def handle(self, *args, **options):
        root = Path(settings.MEDIA_ROOT).resolve()
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S-%f")
        target = Path(options["output"] or settings.BASE_DIR / ".local/backups" / f"materials-{stamp}.tar.gz")
        if target.resolve().is_relative_to(root):
            raise CommandError("备份文件不能放在课程资料目录内部。")
        target.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        try:
            with open(target, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as stream:
                with tarfile.open(fileobj=stream, mode="w:gz", dereference=False) as archive:
                    if root.exists():
                        for path in root.rglob("*"):
                            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
                                archive.add(path, arcname=str(Path("media") / path.relative_to(root)), recursive=False)
                                count += 1
        except FileExistsError as exc:
            raise CommandError("目标已存在，请使用新的备份文件名。") from exc
        self.stdout.write(self.style.SUCCESS(f"课程资料备份完成：{count}个文件，{target}"))
