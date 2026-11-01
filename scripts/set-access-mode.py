"""Explicitly choose HTTP trial or HTTPS while preserving existing secrets."""
import argparse
from datetime import datetime, timezone
import ipaddress
import os
from pathlib import Path
import re
import tempfile
import uuid


def validate_host(host, http_trial):
    if host != host.strip() or len(host) > 253:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return http_trial and ip.version == 4
    except ValueError:
        return "." in host and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in host.split("."))


def configure(target, host, http_trial):
    if not validate_host(host, http_trial):
        raise ValueError("请输入单独的IPv4或域名，不含http://、端口、路径；HTTPS正式模式请填写已配置好的域名。")
    if not target.is_file() or target.is_symlink():
        raise ValueError("请在已有部署目录使用现有普通.env文件；不会创建新密钥或修改链接文件。")
    content = target.read_text(encoding="utf-8")
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    keys = {m.group(1) for line in content.splitlines() if (m := pattern.match(line))}
    if "DJANGO_SECRET_KEY" not in keys:
        raise ValueError("现有配置中缺少DJANGO_SECRET_KEY绑定，请先确认原部署文件，不会覆盖或生成新密钥。")
    settings = {
        "CLASSROOM_DOMAIN": host,
        "CLASSROOM_SCHEME": "http" if http_trial else "https",
        "CLASSROOM_ALLOW_INSECURE_HTTP": "1" if http_trial else "0",
    }
    lines = []
    for line in content.splitlines(keepends=True):
        match = pattern.match(line)
        if match and match.group(1) in settings:
            continue
        lines.append(line)
    preserved = "".join(lines)
    result = preserved + ("\n" if preserved and not preserved.endswith("\n") else "")
    result += "".join(f"{key}={value}\n" for key, value in settings.items())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target.with_name(f".env.access-backup-{stamp}-{uuid.uuid4().hex[:6]}")
    with open(backup, "x", opener=lambda p, flags: os.open(p, flags, 0o600), encoding="utf-8", newline="") as f:
        f.write(content)
    fd, temporary = tempfile.mkstemp(prefix=".env.access-", dir=target.parent)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(result)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return backup


def main():
    parser = argparse.ArgumentParser(description="保持密钥不变，配置访问协议与登录Cookie。")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--http-trial", action="store_true", help="明确启用不加密的HTTP功能试用")
    mode.add_argument("--https", action="store_true", help="切换到已有可信证书与解析的HTTPS域名")
    parser.add_argument("--host", required=True, help="实际IPv4或域名，不含协议或路径")
    args = parser.parse_args()
    target = Path(__file__).resolve().parent.parent / ".env"
    try:
        backup = configure(target, args.host.lower(), args.http_trial)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"已更新访问模式并保留原密钥，私有配置备份：{backup.name}")
    if args.http_trial:
        print("HTTP试用：密码和反馈不会加密，仅用于功能测试。正式教学请配置HTTPS。")
    print("下一步：sudo docker compose up -d --build --wait --wait-timeout 180")


if __name__ == "__main__":
    main()
