# MathAI课堂名称与会话管理更新

本次以 `12aeaba` 为基础，修正课堂名称显示、统一MathAI名称，并增加师生会话删除。升级保留原账号、课堂、文件、反馈、答疑和AI会话。

## 使用方法

“关联课堂”现在显示“课程名称 / 课堂名称（课堂码）”，不再显示 `Lesson object`。课堂码帮助区分同名课堂。学生只能选择已加入课堂，教师只能选择自己创建的课堂，已删除课堂不出现在选项中。学生尚未加入时，先从“我的学习”输入课堂码加入。

从课堂点击“本课堂MathAI”会自动选中该课堂；会话标题下方和“我的会话”也显示对应课程、课堂名称。已有会话无需重建。

问答方式、服务状态、会话回答标题统一显示 **MathAI**。本次只调整名称：MathAI仍检索课程文字并列来源，不会因此变成大模型，也不自动读取图片、PDF/PPT。旧回答原文保留，外部模型的配置沿用[前次教程](学生提问与MathAI答疑归档更新教程.md)。

删除会话：

1. 在“我的会话”找到目标，点击旁边“删除”；或进入会话点击“删除当前会话”。
2. 确认页显示标题、关联课堂和说明。
3. 点击“取消，保留会话”不删除；点击“确认删除会话”才执行。

确认后，该会话及问答从当前数据库删除，页面无法恢复，原地址不能继续访问。不会删除其他会话、课堂、资料、学生反馈或教师答疑。教师不能删除学生的私人会话，学生不能删除其他账号的会话；仍有问题正在处理时需稍后再删除。

已发生的外部模型请求仍计入北京时间当天的个人和全站额度，删除会话不重置次数。系统单独保存日期、调用次数，不靠保留问题正文计数。已有备份按原保存规则保留。

示例均为虚构课堂：[课堂名称与MathAI](images/mathai-classroom-selector.png) · [手机删除确认页](images/mathai-delete-mobile.png)。

## 在原服务器逐步更新

仍在原服务器 `/opt/mathsxnu` 操作。每组命令分别执行，成功后再继续。

### 1. 检查改动和原数据位置

```bash
cd /opt/mathsxnu
sudo git status --short
```

没有输出即可继续。若仍有之前三处本地配置修改，先按[配置备份与暂存说明](课程学习与答疑六项功能更新.md#先处理您之前的本地改动)处理；其他未知改动先保留并确认用途，不强制覆盖。

尚未确认原持久卷时执行：

```bash
sudo docker compose exec -T web python -c "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','mathsxnu.settings'); django.setup(); from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
sudo docker inspect mathsxnu-classroom-web-1 --format '{{range .Mounts}}{{println .Type .Name .Destination}}{{end}}'
```

应看到 `/data/db.sqlite3` 和 `volume mathsxnu-classroom_classroom_data /data`。不一致时先停止换配置，核对原数据库位置，以免读取到空数据库。

### 2. 备份

```bash
sudo bash scripts/backup-server.sh
```

已有文件上传功能的版本应生成数据库和资料压缩包，保存在 `backups/`。压缩包包含教师课件、学生附件；更早无资料库的版本只备份数据库。备份失败不继续。

### 3. 下载新版并构建

```bash
sudo git pull --ff-only origin main
ls feedback/migrations/0008_mathai_usage.py
sudo docker compose build web
```

应显示迁移文件，构建成功后才继续。原 `.env` 的网站地址、密钥、模型配置沿用，不重新运行首次部署向导。构建失败时旧网站仍可运行。

### 4. 暂停入口并做最后备份

选择不进行教学的时间：

```bash
sudo docker compose stop gateway
sudo bash scripts/backup-server.sh
```

网站此时短暂不可访问。若备份失败且尚未启动新版，可用 `sudo docker compose start gateway` 恢复旧服务。

### 5. 启动并检查

```bash
sudo docker compose up -d --no-build --force-recreate --wait --wait-timeout 180
sudo docker compose ps
sudo docker compose exec -T web python manage.py showmigrations feedback
sudo docker compose exec -T web python manage.py check_login_access
```

应看到web为 `healthy`、gateway运行，以及 `[X] 0008_mathai_usage`。迁移新增独立用量计数并回填原外部请求次数，不删除或改写已有会话内容，继续使用原数据卷。

失败时查看 `sudo docker compose logs --tail=80 web gateway`，保留日志与备份，不自行反向迁移，不执行 `docker compose down -v`。提供错误时隐藏个人信息，不发送 `.env` 或密钥。

### 6. 刷新、验收

Windows按 `Ctrl+F5`，安卓关闭旧标签页重新打开原网址。

1. 学生确认选项是已加入课堂的实际名称。
2. 教师确认只出现自己创建的课堂。
3. 确认显示“MathAI”，旧会话仍能打开。
4. 新建测试会话，先删除后取消，再确认删除，核对其他会话保留。使用测试会话验收，避免删掉需要保存的问答。

原网址和访问模式沿用，本次不会自动切换HTTP/HTTPS。

## 验证范围

113项Django测试覆盖课堂名与权限、删除确认、跨账号隔离、CSRF、正在处理请求保护、删除后额度保留和旧库用量按北京时间回填。真实Chromium验证师生实际课堂名称、MathAI命名、取消和确认删除、手机界面，并回归原有教学流程。测试使用临时数据库和虚构数据；外部模型仍只做模拟协议测试。

代码上传GitHub后，仍需完成上述更新才会在您的公网网站生效。
