# V10 部署手册

本文用于 Linux、Docker、宝塔环境。仓库地址为 <https://github.com/PoweredLin/BlogWeb_vp>，分支为 main。生产数据只来自服务器停写备份；本机 data/demo-v10 只能用于演示。

## 1. 准备

在服务器确认 Docker、Compose、磁盘和时间正常：

    docker --version
    docker compose version
    docker info

准备独立目录，例如 /www/wwwroot/lin-notebook-v10，将同一版本的源码或镜像包放入目录。不要上传 .env、data、backups、node_modules、.venv 或测试结果。

复制配置并仅修改服务器上的 .env：

    cd /www/wwwroot/lin-notebook-v10
    cp .env.example .env
    chmod 600 .env

关键配置：

    APP_ENV=production
    SITE_URL=https://lolicong.xyz
    COOKIE_SECURE=true
    FORWARDED_ALLOW_IPS=172.30.17.1
    EMAIL_ENCRYPTION_KEY=稳定保存的Fernet密钥

SITE_URL 必须是浏览器访问的 HTTPS origin。EMAIL_ENCRYPTION_KEY 只在需要邮件功能时设置；生成一次后长期保留，更换会使已保存的 SMTP 授权码无法解密。

## 2. 镜像

有 Docker 构建环境时：

    docker compose config --quiet
    docker compose build
    docker image inspect lin-notebook:10 --format '{{.Os}}/{{.Architecture}}'

2 核 4G 服务器推荐在本地构建后导出并上传：

    docker compose build
    docker save -o lin-notebook-v10.tar lin-notebook:10

服务器导入：

    docker load -i lin-notebook-v10.tar

## 3. 迁移生产数据

先记录旧项目实际状态和挂载：

    docker compose ps
    docker compose config
    docker inspect <旧容器> --format '{{json .Mounts}}'
    ss -ltnp | grep -E ':4317|:4318'

在维护窗口停止实际写入生产库的旧程序。确认旧程序已停后，复制 SQLite 及 uploads/ 到 V10 目录的 data/；不要复制为 data/data/。同时保留停写时刻的完整副本到服务器外部。已有文章、评论和图片不能用本机演示库覆盖。

    mkdir -p data backups
    cp -a /旧项目/data/space.sqlite data/
    cp -a /旧项目/data/uploads data/
    cp -a data backups/pre-v10-production-data
    chown -R 10001:10001 data backups
    chmod 700 data backups

迁移启动会自动创建 data/migration-safety/before-v10.sqlite。不要同时让两个版本写同一 SQLite，也不要运行 docker compose down -v。

## 4. 启动与验收

    docker compose up -d --no-build
    docker compose ps
    docker compose logs --tail=100 space
    docker compose port space 4317
    curl -fsS -H 'Host: lolicong.xyz' http://127.0.0.1:<实际宿主机端口>/healthz
    curl -fsS -H 'Host: lolicong.xyz' http://127.0.0.1:<实际宿主机端口>/api/status

健康检查应返回 {"ok":true,"version":"10.0.0"}，已有站点的 /api/status 应为 setup:false。实际宿主机端口以 docker compose port 为准，不能假设是 4317 或 4318。

全新空站点只能使用离线初始化：

    docker compose run --rm space python -m backend.cli owner-init

生产网页初始化已关闭，没有内置默认密码。忘记密码使用 owner-reset，不会删除内容。

## 5. 宝塔/Nginx

在 HTTPS 站点的唯一 location / 中反代到上一步确认的端口。例如端口为 4318：

    client_max_body_size 12m;
    client_body_timeout 30s;

    location / {
        proxy_pass http://127.0.0.1:4318;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

不要把 Host 写成 127.0.0.1，否则站点来源校验会返回“无效主机名”。不要把旧静态目录接回 try_files。宝塔配置检查通过后 reload Nginx，再从 HTTPS 域名无痕窗口验证首页、登录、文章、图片、草稿、评论审核和管理页。

## 6. 备份与回滚

维护窗口停写后执行完整备份：

    docker compose stop space
    docker compose run --rm space python -m backend.cli backup --destination /app/backups/full-2026-11-06
    docker compose start space

备份包括 SQLite、上传目录和备份说明，复制一份到服务器外部。回滚时停止 V10，恢复旧镜像与同一停机时刻的数据副本，再把 Nginx 指回旧端口。V10 已产生的新内容应先另行导出和人工合并，不能直接用旧副本覆盖。保留旧镜像、旧目录、.env 密钥和备份，稳定观察后再清理。

## 7. 常见问题

- setup:true：检查挂载是否指向正确的 data/space.sqlite，不要在已有站点重新初始化。
- 登录后退出：检查 HTTPS、SITE_URL、COOKIE_SECURE 和 Host $host。
- 图片 404：确认 data/uploads/ 完整，私有草稿图片不会对匿名用户开放。
- 邮件不能发送：设置稳定的 EMAIL_ENCRYPTION_KEY，使用 SMTP 授权码并核对 465/隐式 TLS 或 587/STARTTLS；见邮件排查。
- Git 动态变慢：应用已使用缓存、ETag、超时和退避；不要把 token 放进前端或反复强制刷新。

当前本地没有可用 Docker Engine 时，不能把镜像构建、容器重启和服务器迁移标记为已验证；应在 Linux 服务器或可用 Docker 环境执行上述验收。
