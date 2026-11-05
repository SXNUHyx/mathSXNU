# d4aae6a 专用更新教程：学生反馈与答疑问题图谱

功能提交：`d4aae6a77c31a11380163110d98e56f122c77ebc`。本页为问题图谱版本独立教程。GitHub提供本版代码和离线工具；腾讯云仍需按下列步骤更新后生效。

## 本次新功能

在教师看板“学生反馈与答疑”内增加“问题图谱”，自动展示本课堂当前的课堂—模块—问题关键词关联。点击节点查看相关学生、学号、问题片段、答疑状态及回复入口；支持疑惑/求助、未回答/已回答筛选，键盘选择、约5秒更新和手机横向滑动。可折叠图谱继续使用原列表。

图谱只使用本课堂最新黄/红反馈，不读取附件、私有MathAI会话或其他课堂。每个关键词最多对应每份当前反馈一次；连线来自实际模块归属和同份反馈中的关键词共现，不表示自动推断的因果或先修关系。当前反馈图谱与累计追问统计用途不同，历史答疑仍保留在原归档。

最多展示优先未回答的前300份当前反馈；超限明确提示总量。图中显示前12个关键词和前8个模块，其余模块合并为“其他模块”，根节点与相关问题列表仍覆盖这批采样反馈。没有文字的问题仍出现在课堂/模块节点与问题列表中。权限沿用教师本人课堂及开发者管理员管理权限。无需新增依赖或数据库迁移。

## 本版专用下载链接

- [下载本版离线更新工具 import-update-d4aae6a.py](https://raw.githubusercontent.com/SXNUHyx/mathSXNU/main/scripts/import-update-d4aae6a.py)
- [下载本版源码ZIP](https://github.com/SXNUHyx/mathSXNU/archive/d4aae6a77c31a11380163110d98e56f122c77ebc.zip)

离线工具内含本版Git更新数据，无需另外下载ZIP或bundle；不要套用之前的工具。支持从7bf829c、9c3c36d、c429ce0、a9759a8、c785981、dcf12c6升级。其他起点先核对，不能强制覆盖。

## 腾讯云更新步骤

1. 电脑浏览器下载 `.py` 文件并保留文件名 `import-update-d4aae6a.py`；浏览器显示代码时右键另存为，不保存成.py.txt。上传至腾讯云文件管理 `/root`。不要把文件路径直接当命令执行。

2. 核对原项目和版本：

```bash
sudo ls -lh /root/import-update-d4aae6a.py
cd /opt/mathsxnu
sudo git log -1 --oneline
sudo git status --short
sudo docker compose ps
```

应为原项目，Git状态无输出，web和gateway是原部署。有本地修改或目录不同先停止，保留输出核对。

3. 校验文件及适用版本：

```bash
echo 'ab729d001a97e4eb7070560bdd9c951d1d7f7c07d572db46f844a5c01f24bd1d  /root/import-update-d4aae6a.py' | sudo sha256sum -c -
sudo python3 /root/import-update-d4aae6a.py --check
```

成功再继续。脚本遇到版本不符、本地改动或校验失败会停止，不覆盖项目。

4. 先备份数据库与课程文件，成功再导入：

```bash
sudo bash scripts/backup-server.sh
sudo python3 /root/import-update-d4aae6a.py
sudo git log -1 --oneline
sudo git status --short
```

必须逐条执行，备份失败就停止。预期日志为d4aae6a、Git状态无输出。保留原.env、账号、课程资料、Docker卷和域名配置。导入阶段不访问GitHub，保留原Git历史。

5. 构建成功后暂停入口，再备份一次：

```bash
sudo docker compose build web
sudo docker compose stop gateway
sudo bash scripts/backup-server.sh
```

逐条执行，构建失败先停止，不暂停原网站；第二次备份失败且尚未替换web时，执行 `sudo docker compose start gateway` 恢复入口。

6. 第二次备份成功后启动并检查：

```bash
sudo docker compose up -d --no-build --force-recreate --wait --wait-timeout 180
sudo docker compose ps
sudo docker compose exec -T web python manage.py check
sudo docker compose exec -T web python manage.py migrate --check
```

预期web healthy、gateway运行，检查通过。异常时查看 `sudo docker compose logs --tail=80 web gateway`，保留备份，不执行 `docker compose down -v`。

## 页面验收

Ctrl+F5刷新，用测试课堂检查：

1. 提交包含“方差”“数学期望”等文字、关联不同模块的疑惑或求助，图谱出现对应模块与关键词。
2. 点击关键词，右侧显示相关问题和回复入口；切换反馈类型及答疑状态筛选。
3. 另一看板保持前台，教师回复后约5秒图谱答疑状态更新；学生再次提问重新成为未回答。
4. 手机页面不横向撑开，图谱区域可左右滑动；空课堂显示无符合条件问题。
5. 普通学生及其他教师不能访问本课堂教师看板；开发者管理员按原权限可访问。

本版161项Django测试通过；浏览器验证节点点击、键盘筛选、答疑后轮询更新及桌面/手机布局，原师生浏览器流程通过。离线工具另在临时仓库验证支持版本导入及配置/模拟数据保留。开发检查不代表腾讯云已更新。
