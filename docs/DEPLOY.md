# V9 部署与从线上 V8 升级

适用环境：宝塔、2 核 4G、域名已绑定、Nginx 提供 HTTPS。仓库：<https://github.com/PoweredLin/BlogWeb_vp>。

**线上已经写过文章和上传图片。必须搬服务器的 `data`，不能用本地测试数据覆盖。** 新版仍使用 SQLite；不需要把文章导出后重新发布。

## 1. 准备新目录

保留正在运行的 V8 和反向代理。先部署到新目录，例如 `/www/wwwroot/lin-notebook-v9`。

```sh
cd /www/wwwroot
git clone --branch main https://github.com/PoweredLin/BlogWeb_vp.git lin-notebook-v9
cd lin-notebook-v9
cp .env.example .env
chmod 600 .env
```

`.env` 与 `compose.yaml` 同目录，不放在 `public` 中。修改复制出来的 `.env`，不要只修改 `.env.example`。

```dotenv
APP_ENV=production
SITE_URL=https://lolicong.xyz
COOKIE_SECURE=true
FORWARDED_ALLOW_IPS=172.30.17.1
```

`SITE_URL` 必须与浏览器使用的 HTTPS 域名完全一致，不带路径或末尾 `/`。如果同时使用 www 与裸域，请由 Nginx 把另一个域名 301 到这个地址。否则写入请求会被来源检查拒绝。

Compose 默认使用独立网络 `172.30.17.0/24`，网关 `172.30.17.1`。如与服务器其他网络冲突，同时修改 Compose 子网和 `.env` 的受信任网关。不要设 `FORWARDED_ALLOW_IPS=*`。宝塔代理必须覆盖 `X-Forwarded-For`，避免客户端伪造来源绕过频率限制。

## 2. 构建镜像

安装 Docker Engine 与 Compose 插件，确认：

```sh
docker --version
docker compose version
docker compose config --quiet
docker compose build
```

Python 官方源下载慢时，可仅对本次构建指定可信 HTTPS 镜像源，不修改应用运行配置：

```sh
docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

首次构建下载 Node/Python 基础镜像和依赖，需要访问镜像源。构建较耗内存；对 2 核 4G 主机，更推荐在自己的电脑构建后传镜像：

```sh
# 本地项目目录
docker compose build
docker save -o lin-notebook-v9.tar lin-notebook:9
# 用宝塔文件管理器/SFTP 上传 tar 到服务器，再执行
docker load -i lin-notebook-v9.tar
```

镜像不包含 `.env`、数据库、上传图片、旧 ZIP、历史备份、测试截图。运行时只需要 Python，不安装 Node 后端。镜像装好后可删传输用 tar，保留上一个镜像用于回滚。

## 3. 迁移线上数据

先在旧站停止写入：维护时段停止旧 PM2/宝塔 Node 项目或旧容器。**只停止实际部署的那种进程，不要同时启动两份服务写同一个数据库。**

如果旧版使用主机目录 `/www/wwwroot/lin-notebook/data`，停止旧服务后执行：

```sh
cd /www/wwwroot/lin-notebook-v9
mkdir -p backups
cp -a /www/wwwroot/lin-notebook/data ./data
cp -a ./data ./backups/pre-v9-production-data
sudo chown -R 10001:10001 ./data ./backups
sudo chmod 700 ./data ./backups
```

如 `./data` 已存在，先检查它的来源和内容，不要重复执行 `cp` 导致 `data/data`，不要覆盖已有新数据。应看到 `data/space.sqlite`、`data/uploads/`。SQLite 的 `-wal`/`-shm` 如存在也要随停机目录一起复制；不要只复制正在运行的主数据库文件。

如果旧版用的是 Docker 命名卷，先检查旧容器的 Mounts 获取实际卷名：

```sh
docker inspect <旧容器名称> --format '{{json .Mounts}}'
```

停止旧容器后，通过只读挂载旧卷的临时容器导出整个 `/app/data`，或使用 `docker cp <已停止旧容器>:/app/data ./data`。导出后同样做独立备份、校验路径、设置 UID 10001 权限。**不要运行 `docker compose down -v`，这会删除旧数据卷。**

已有站点不需要再初始化账号。旧账号和密码哈希直接兼容；站主用户名仍为 `admin`。不要导入本地 `data/space.sqlite`。

## 4. 启动与本机验证

确保旧服务已经释放 4317 端口，然后：

```sh
cd /www/wwwroot/lin-notebook-v9
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=100 space
curl -fsS http://127.0.0.1:4317/healthz
curl -fsS http://127.0.0.1:4317/api/status
```

`healthz` 返回 `{"ok":true,"version":"9.0.0"}`。已有站点的状态应为 `setup:false`；未登录时 `authenticated:false` 正常。`setup:true` 表示没有站主账号，应该先检查是否挂载了正确数据库。

首次读取 V8 数据库会创建 `data/migration-safety/before-v9.sqlite`，再增量升级。启动日志如有权限错误，检查 `data` 和 `backups` 的 UID/GID，而不是放开整个项目的写权限。

只在**全新空站点**初始化：

```sh
docker compose run --rm space python -m backend.cli owner-init
```

交互输入昵称与至少 10 字符的密码。生产环境关闭网页初始化入口，不提供通用默认密码。

## 5. 宝塔反向代理

网站域名绑定 `lolicong.xyz`，申请并启用 SSL。代理目标：`http://127.0.0.1:4317`。原先静态测试站点的首页、另一条 `location /` 和跳转规则不要继续接管这个域名。

下列内容放在对应 HTTPS `server` 的配置中；已有 `location /` 要替换，不能重复添加：

```nginx
client_max_body_size 12m;
client_body_timeout 30s;

location / {
    proxy_pass http://127.0.0.1:4317;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;
}
```

不要配置 `try_files ... /index.html` 指向旧目录，不要把项目根目录作为静态下载站。应用自行处理 Vue 历史路由。4317 只绑定回环地址，不用在云安全组开放；公网只开放 80/443 及你自己的管理端口。

宝塔先“配置检查”，成功后重载 Nginx。浏览器通过 HTTPS 域名测试，Secure Cookie 不能用于普通 HTTP 登录。

## 6. 上线验收

1. 无痕窗口打开首页、现有两篇文章、说说和相册，确认图片与原链接正常。
2. 站主登录，检查文章数量、图片、私人记录、两套主题和设置。
3. 新建草稿，修改、预览、删除；确保草稿不在公开页面出现。
4. 留言后无痕窗口不可见，审核通过后可见。
5. 读者不能访问 `/api/private/state`、管理或写文章入口。
6. Git 日历首次可能显示后台同步，稍后点击刷新；平台故障不会阻塞其他页面。
7. 重启 `docker compose restart`，确认文章、设置、图片仍在。

首次切换请硬刷新或清站点缓存；API 与 HTML 使用 `no-store`，构建资源使用内容 hash。若仍看到旧页面，检查 DNS、Nginx 实际站点、代理缓存和是否连到了旧服务，不能仅靠末尾 `/` 判断版本。

## 7. 全站备份

界面内的 JSON 备份沿用个人记录格式，**不等于全站备份**。完整备份必须包含 SQLite 和 `uploads`。

维护窗口暂停写入后：

```sh
docker compose stop space
docker compose run --rm space python -m backend.cli backup --destination /app/backups/full-2026-10-26
docker compose start space
```

目标备份目录必须不存在。备份命令使用 SQLite backup API，复制数据库及整个上传目录。将完整备份同步到另一台机器；不要把它提交到 Gitee。定期用临时目录运行 `python -m backend.cli check --data-dir <备份目录>` 检查数据库，并抽查文章图片。

数据库备份包含密码哈希、注册记录和私人内容，应和 `.env` 一样保护。可删除根目录过时 MD 而不影响运行，但建议保留本部署文档；新版发布目录已经整理过，不需要再随意删文件。

## 8. 更新与回滚

更新前保存旧代码版本/镜像和完整数据备份。拉取更新、构建成功后，停写备份，再替换容器。不要在新版已经产生数据之后直接拷回一个月前的数据库。

V9 的数据库改动为新增表/索引，原内容字段保持兼容；回滚仍建议使用**同一停机时刻**的旧镜像与旧数据副本，并先在隔离端口验证。回滚后再恢复写入。V9 新写的数据若必须保留，先导出并人工合并，不能盲目覆盖。

## 9. 常见问题

- **登录被拒绝 / 403**：检查浏览器 HTTPS 地址与 `SITE_URL`，确认代理传递原 Host；不要关闭来源验证。
- **登录后又退出**：用 HTTPS；检查 Secure Cookie、系统时间、容器是否使用同一个数据目录。
- **短旧密码无法更改**：登录兼容旧密码，新密码必须至少 10 字符。忘记密码执行 `docker compose run --rm space python -m backend.cli owner-reset`，不会删除文章。
- **图片 404**：未被公开文章/相册/公开设置引用的图片仅站主或上传者可见；同时检查 uploads 是否迁移完整。
- **数据库为空**：`setup:true` 不是成功初始化的意思，检查挂载和 `data/data` 路径。
- **Git 不立即更新**：缓存与平台冷却是预期行为，反复点刷新不会绕过限流。不要把 GitHub token 写进前端。
- **镜像拉取失败**：在有可用网络的电脑构建并 `docker save/load`，或配置可信镜像源；不要关闭 TLS 校验。
- **服务器内存不足**：在本地构建；运行容器默认限制 768MiB。查日志和 `docker stats --no-stream`，不要直接增加并发 worker。
