"""Create a private deployment .env without printing its generated secret."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import secrets


def valid_domain(value):
    if not value or len(value) > 253 or "." not in value:
        return False
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        pass
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in value.split(".")):
        return False
    if value in {"example.com", "example.cn", "example.edu.cn"} or value.endswith((".example.com", ".example.edu.cn")):
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="填写课堂域名，自动生成私有部署配置。")
    parser.add_argument("--domain")
    args = parser.parse_args()
    target = Path(__file__).resolve().parent.parent / ".env"
    if target.exists():
        print("已有 .env 配置，未覆盖。要调整域名，请由维护者编辑已有配置。")
        return
    domain = (args.domain if args.domain is not None else input("请输入您的真实课堂域名（不要输入https://）：")).strip().lower()
    if not valid_domain(domain):
        parser.error("请输入已准备好的真实域名，例如课堂子域名；不能填IP、示例域名、网址路径或端口。")
    try:
        with open(target, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
            f.write(f"CLASSROOM_DOMAIN={domain}\nDJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n")
    except FileExistsError:
        print("配置已存在，未覆盖。")
        return
    print(f"已生成私有配置：{target.name}；域名为 {domain}。")
    print("密钥未显示在屏幕上。不要把 .env 上传到GitHub，也不要发送给他人。")
    print("下一步：sudo docker compose up -d --build")


if __name__ == "__main__":
    main()
