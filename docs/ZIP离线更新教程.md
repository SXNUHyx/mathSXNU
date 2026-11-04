# 腾讯云 ZIP 离线更新：保留数据、配置和 Git 历史

当服务器访问 GitHub 443 超时，先按 Ctrl+C 结束等待。改用电脑浏览器下载官方源码ZIP，再通过腾讯云文件管理上传。不能将ZIP路径直接当作命令运行；不要直接把ZIP整包覆盖原项目，也不要新建一份生产部署。

## 已核对的实际案例：7bf829c → 9c3c36d

以下命令仅对应这个已核对的版本组合。后续更新应为相应目标版本重新生成并校验导入脚本，不能只替换下面的提交编号，也不能把此脚本用于最新main的任意ZIP。

1. 在电脑浏览器下载 [9c3c36d源码ZIP](https://github.com/SXNUHyx/mathSXNU/archive/9c3c36df6554f7e2609b3011b371cb18265f78b4.zip)，上传到腾讯云文件管理。本例中上传位置为 `/root/mathSXNU-update.zip`，Ubuntu普通账号需要sudo读取。
2. 在服务器核对文件、原版本和本地修改：

```bash
sudo ls -lh /root/mathSXNU-update.zip
cd /opt/mathsxnu
sudo git log -1 --oneline
sudo git status --short
sudo python3 -c "import zipfile; z=zipfile.ZipFile('/root/mathSXNU-update.zip'); print('\n'.join(z.namelist()[:10]))"
```

应为7bf829c且无本地修改，ZIP顶层目录为 `mathSXNU-9c3c36df6554f7e2609b3011b371cb18265f78b4/`。版本或路径不一致时先停止，核对实际情况。不要使用强制重置。

3. 备份数据库及上传资料；成功后才继续：

```bash
sudo bash scripts/backup-server.sh
```

4. 整段复制执行以下导入脚本。它逐一校验5份变更文件、完整版本树和原Git提交，使用临时索引导入原提交，再执行快进合并。它不覆盖 `.env`、Docker卷或本地课堂数据；版本不符、校验失败或存在本地改动时会停止。

```bash
sudo python3 - <<'PY'
import base64, os, subprocess, tempfile, zipfile
from pathlib import Path

project = Path('/opt/mathsxnu')
archive = Path('/root/mathSXNU-update.zip')
old = '7bf829cc4ec49d5391be4d12ceab51601954b371'
new = '9c3c36df6554f7e2609b3011b371cb18265f78b4'
files = {
    'README.md': 'd9596f762cb904e0b688e95212549a588e09f268',
    'docs/课程管理与反馈分组更新教程.md': '3dab3153d4b5cfaf5c60ea3dd3f595fffb55b880',
    'feedback/test_feedback_order.py': '80ab3de36d6c738034dd9b8ea940e4f1f6f39af8',
    'feedback/views.py': 'b25f4bb45148d1c30993df1f32dbcc755155c122',
    'scripts/developer_smoke.py': '03cf26df4fbaad68601d86a594b1660d19bb10b6',
}
def git(*args, data=None, env=None):
    return subprocess.check_output(['git', '-C', str(project), *args], input=data, env=env).decode().strip()

if git('rev-parse', 'HEAD') == new:
    print('已是目标版本，无需再次导入。')
    raise SystemExit(0)
if git('rev-parse', 'HEAD') != old or git('status', '--porcelain'):
    raise SystemExit('版本不符或存在本地改动，已停止；未覆盖项目文件。')
with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory(prefix='mathsig-import-') as tmp:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
    git('read-tree', old, env=env)
    for name, expected in files.items():
        data = z.read('mathSXNU-' + new + '/' + name)
        actual = git('hash-object', '-w', '--stdin', data=data)
        if actual != expected:
            raise SystemExit('文件校验失败：' + name + '；未覆盖项目文件。')
        git('update-index', '--add', '--cacheinfo', '100644', actual, name, env=env)
    if git('write-tree', env=env) != '935565e8ffc60389aa8ffc683b2580df95f22d69':
        raise SystemExit('版本树校验失败；未覆盖项目文件。')
    raw = base64.b64decode('dHJlZSA5MzU1NjVlOGZmYzYwMzg5YWE4ZmZjNjgzYjI1ODBkZjk1ZjIyZDY5CnBhcmVudCA3YmY4MjljYzRlYzQ5ZDUzOTFiZTRkMTJjZWFiNTE2MDE5NTRiMzcxCmF1dGhvciB5eCBoIDxoeXg4NTQ1OTRAZ21haWwuY29tPiAxNzkzNzk1NTkwICswMDAwCmNvbW1pdHRlciB5eCBoIDxoeXg4NTQ1OTRAZ21haWwuY29tPiAxNzkzNzk1NTkwICswMDAwCgpQcmlvcml0aXplIHVuYW5zd2VyZWQgZmVlZGJhY2sgYW5kIG1vdmUgY3VycmVudCByZXBsaWVzIHRvIHRoZSBlbmQK')
    if git('hash-object', '-w', '-t', 'commit', '--stdin', data=raw) != new:
        raise SystemExit('提交校验失败；未覆盖项目文件。')
subprocess.run(['git', '-C', str(project), 'merge', '--ff-only', new], check=True)
print('离线更新完成，当前版本：', git('rev-parse', '--short', 'HEAD'))
PY
```

预期最后显示“离线更新完成，当前版本：9c3c36d”。再次执行会识别已更新版本而退出。提交历史与GitHub一致，网络恢复后仍可继续正常拉取。

5. 构建镜像。此处仍可能需要访问镜像或依赖仓库；代码离线导入成功不代表镜像下载一定可用。构建失败时停止，不替换旧服务。

```bash
sudo docker compose build web
```

构建成功后暂停入口，再备份一次：

```bash
sudo docker compose stop gateway
sudo bash scripts/backup-server.sh
```

若第二次备份失败且尚未替换web，用 `sudo docker compose start gateway` 恢复旧入口，停止升级并排查。

6. 第二次备份成功后启动新版：

```bash
sudo docker compose up -d --no-build --force-recreate --wait --wait-timeout 180
sudo docker compose ps
sudo docker compose exec -T web python manage.py check
sudo docker compose exec -T web python manage.py migrate --check
sudo git log -1 --oneline
sudo git status --short
```

预期web为healthy，版本9c3c36d，Git状态无输出。失败时查看 `sudo docker compose logs --tail=80 web gateway`，保留备份与原卷，不执行 `docker compose down -v`。

7. 浏览器Ctrl+F5刷新，在测试课堂验收回复后排序，核对原账号、课堂和课程资料仍在。

## 后续每次离线更新需核对的项目

- 原服务器实际提交、Git状态、项目路径和数据卷；保留原 `.env`。
- 官方下载链接对应的目标提交、ZIP实际上传路径及其顶层目录。
- 为这次起止版本配套生成的导入脚本，包含文件、版本树及提交校验；本页固定脚本只能用于上述案例。
- 先备份、导入、构建，再暂停入口二次备份，最后启动和验收。不要将源码ZIP与Git bundle的导入命令混用。

本页导入脚本已在临时仓库实际验证：从7bf829c导入ZIP后得到原9c3c36d提交，Git状态干净，本地配置和模拟数据库保留，再次执行安全退出。腾讯云服务器的最终结果仍以实际终端输出为准。
