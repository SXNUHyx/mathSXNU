# HTTP公网IP访问：注册成功后仍回到登录页

## 发生了什么

用户反馈：使用 `http://公网IP/` 打开平台，教师和学生注册后登录，仍回到登录页。

原生产配置默认只允许通过HTTPS保存登录和CSRF Cookie。HTTP公网IP访问与此不一致时，浏览器可能无法保存会话；仅修改“登录后跳去哪里”不能解决访问协议冲突。

本次增加一个需要明确启用的HTTP功能试用模式，统一网关协议、CSRF来源、登录Cookie和HTTPS跳转。默认仍然是HTTPS，不会因为请求是HTTP而自动降低安全设置。

**HTTP不加密密码和反馈。以下模式用于功能试用，请使用测试账号，不收集真实学生敏感数据；正式教学请配置域名和可信HTTPS证书。** 试用模式在每个页面显示提示。

## 原服务器更新步骤

不需要重新注册账号，不需要重置数据库或生成新密钥。请在暂时不使用网站时操作，构建和重启可能造成短暂停站。代码框逐组执行，前一步成功后再继续。

1. 打开原云服务器的远程终端，进入原项目并备份：

   ```bash
   cd /opt/mathsxnu
   sudo bash scripts/backup-server.sh
   ```

2. 下载最新代码：

   ```bash
   sudo git pull --ff-only origin main
   ```

   如果提示本地 `compose.yaml` 等文件被改动，停在这里保留报错，不执行强制覆盖。此前为HTTP手动调整过部署文件时，需要先保留这些设置再处理合并。

3. 设置HTTP功能试用。把下方 `YOUR_PUBLIC_IP` 换成您服务器的真实公网IPv4，不加 `http://` 或路径：

   ```bash
   sudo python3 scripts/set-access-mode.py --http-trial --host YOUR_PUBLIC_IP
   ```

   脚本只修改访问模式相关字段，保留原 `DJANGO_SECRET_KEY` 和其他配置，并自动生成权限受限的 `.env.access-backup-...` 私有备份。不要把 `.env` 和这些备份上传GitHub。

4. 构建并重新创建服务，使新的环境变量实际生效：

   ```bash
   sudo docker compose up -d --build --wait --wait-timeout 180
   sudo docker compose ps
   ```

   只执行 `docker compose restart` 不足以加载改变的环境变量。本次没有数据库结构变更，也不删除旧账号或课堂记录。

5. 核对登录访问设置：

   ```bash
   sudo docker compose exec -T web python manage.py check_login_access
   ```

   正确应显示：网站地址为 `http://您的公网IP`，HTTP试用模式已启用，登录Cookie仅限HTTPS为 `False`，CSRF Cookie仅限HTTPS为 `False`，强制HTTPS跳转为 `False`。该命令不输出密钥、密码或Cookie值。

6. 在Windows的Edge或Chrome按 `Ctrl+Shift+N` 打开新的隐私窗口，输入原来的HTTP公网IP网址，用原教师账号登录。

7. 教师应进入“我的课堂”。退出后再用学生账号登录，应进入“我的学习”；从课堂链接登录学生账号，则进入该课堂反馈页。

如果失败，提供第5步的非敏感输出和以下错误日志片段，不发送密码或 `.env` 文件：

```bash
sudo docker compose logs --tail=60 web gateway
```

不要删除数据库、原目录或数据卷，也不要执行 `docker compose down -v`。

## 正式教学切回HTTPS

先准备好真实域名的解析、备案及可信证书所需网络条件，再将下面 `YOUR_CLASSROOM_DOMAIN` 换成实际域名：

```bash
cd /opt/mathsxnu
sudo bash scripts/backup-server.sh
sudo python3 scripts/set-access-mode.py --https --host YOUR_CLASSROOM_DOMAIN
sudo docker compose up -d --build --wait --wait-timeout 180
sudo docker compose exec -T web python manage.py check_login_access
```

此时应使用 `https://真实域名/`，HTTP试用模式未启用，两个安全Cookie设置和HTTPS跳转均为 `True`。确认没有证书警告后再收集真实学生数据。

## 验证范围

开发环境已验证：50项功能、权限与配置测试；非localhost模拟HTTP来源的实际Chromium浏览器中，教师注册、退出重登、学生注册和换设备登录可保持会话；HTTP试用保留HTTPS默认行为。

当前执行环境的网络策略禁止读取用户公网IP，无法直接核对线上响应。因此不能声称已修改或实测用户服务器；必须执行上述更新和自检，再在实际电脑、手机验收。
