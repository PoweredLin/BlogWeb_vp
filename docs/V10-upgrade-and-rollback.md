# V9 → V10 升级与回滚

本文用于将现有线上 V9 数据库升级到 V10。V10 的 SQLite schema 迁移会自动建立 before-v10.sqlite，但这不是完整站点备份。升级前仍需备份数据库、图片、配置和旧镜像。

已完成 V10 升级但后台有 503/样式延迟时，使用 [后台加载补丁与容器排查](后台503与容器排查.md)，只更新程序，不重复复制 v9 数据。以后正式写入以 v10/data 为准。

本次发布代码位于 GitHub `PoweredLin/BlogWeb_vp` 的 `main` 分支，版本号 10.0.0。推荐按本文使用新目录和完整停写备份升级；[发布验收记录](RELEASE-V10.md) 提供复验命令。若服务器已经运行 V10，本次是同版本功能更新，仍需备份和重建镜像，通常不触发新的 schema 迁移。

本次新增：季度海报墙、页面/片头设置、邮件与模板自动化、文档/书架、受限 AI API、主题与字体优化、页脚状态。不会自动改写已有站点名称或建站日期；升级后在博客设置中设为“林间笔记”并填写真实上线时间，在页面布局中设当前季度 auto、数量 10。旧设置优先于新版本默认值。

线上实际端口、容器名、数据挂载、Compose 项目名和 Nginx 配置以服务器现场为准。此前排查曾见到旧 Node 占用 4317、Docker 容器转发 4318；这只是历史记录，不代表当前端口。

## 升级准入

- 本地 V10 功能、后端、浏览器、封面预览测试和生产构建通过。
- 服务器将获取到的源码或镜像与本次验证版本完全一致。使用 `git log -1 --oneline` 核对发布提交，不以目录名或页面相似程度判断升级成功。
- 维护窗口可停写；完整备份已复制到服务器以外，并能读取。
- 已记录旧容器镜像、Compose 项目、实际数据挂载和 Nginx 目标。
- 新目录及候选数据独立于旧站；演示库 data/demo-v10 永远不用于线上。
- 不把真实 .env、SMTP 授权码、Access Token 或生产数据库提交仓库。

## 1. 记录旧站状态

在服务器进入旧版项目目录并记录现场。目录名和容器名需替换为现场值：

    cd /www/wwwroot/lin-notebook-v9
    pwd
    docker compose ps
    docker compose config --quiet
    docker compose port space 4317
    docker inspect <旧容器名> --format '{{json .Mounts}}'
    docker inspect <旧容器名> --format '{{.Image}}'
    ss -ltnp | grep -E ':4317|:4318|:4319'

记录旧镜像的不可变 image ID、容器端口映射、宿主机数据目录或卷名、宝塔 HTTPS 站点中唯一 location / 的 proxy_pass，以及旧服务如何启动。保存当前 Nginx 配置和旧 .env 的离线副本。

如果旧服务不是 Docker，先确认实际启动方式和真实数据路径；不要根据目录名猜测，也不要杀掉不明 PID。

## 2. 准备 V10 候选

在新目录部署已验证的 V10 代码，例如 /www/wwwroot/lin-notebook-v10。确认该版本包含 image lin-notebook:10，健康检查版本为 10.0.0。不要覆盖旧目录。

    cd /www/wwwroot
    git clone --branch main --single-branch https://github.com/PoweredLin/BlogWeb_vp.git lin-notebook-v10
    cd lin-notebook-v10
    git log -1 --oneline

以上 clone 仅用于尚不存在的新目录。若该目录已存在，先检查其 Git 状态；不要在唯一生产目录中覆盖或强制重置。保留旧镜像 ID，还可给其附加便于恢复的标签，例如 `docker image tag <旧镜像ID> lin-notebook:pre-v10`。

生产配置文件 .env 放在 compose.yaml 同级并设为 600。填写原站点 HTTPS origin、Secure Cookie 和可信代理地址；保持原有 EMAIL_ENCRYPTION_KEY 不变。若之前未启用邮件，候选环境先不配置 SMTP，不要为升级临时替换密钥。

    cd /www/wwwroot/lin-notebook-v10
    cp /旧项目目录/.env .env
    chmod 600 .env
    docker compose config --quiet

优先复制原 `.env` 保留域名和密钥，再对照 `.env.example` 补缺项。只有之前确实没有 `.env` 时才复制 example 新建；example 不是实际生效配置，不能覆盖原密钥。

如果本地有 Docker 构建环境，先完成构建和隔离容器测试，再传同一镜像：

    docker compose build
    docker save -o lin-notebook-v10.tar lin-notebook:10

服务器导入：

    docker load -i lin-notebook-v10.tar
    docker image inspect lin-notebook:10 --format '{{.Id}} {{.Os}}/{{.Architecture}}'

当前开发电脑没有可用 Docker Engine；因此本地 Docker 镜像构建与容器验收必须在有 Docker 的 Linux 主机或服务器进行，不能据本地 Python 服务的健康状态推断镜像验收通过。

## 3. 停写、备份和数据复制

先通知站主进入维护窗口。停止实际处理写请求的旧服务；确认容器、宝塔 Node 项目或其他进程均不再写入该数据库。

停写后，在旧 Compose 项目中创建完整快照：

    docker compose run --rm space python -m backend.cli backup --destination /app/backups/pre-v10-2026-11-06

backup 命令生成 space.sqlite、uploads/ 和 backup.txt。通过 docker inspect 的 Mounts 找到 /app/backups 对应的宿主机路径，或从已停止的旧容器 docker cp 导出。将完整快照额外复制到服务器外部，并核对文件大小及目录结构。

该命令应在旧代码和旧镜像仍可用时执行。若原站不具备此 CLI，停止实际写入进程后，完整复制现场确认的 data 目录（包含 space.sqlite、可能存在的 WAL/SHM 与 uploads），不要只抽走运行中数据库的主文件。`.env` 和旧 Compose/Nginx 配置另行备份。旧镜像不要被新构建覆盖后才开始找备份命令。

将快照复制到 V10 目录的 data/：

    mkdir -p /www/wwwroot/lin-notebook-v10/data
    cp -a /备份路径/space.sqlite /www/wwwroot/lin-notebook-v10/data/
    cp -a /备份路径/uploads /www/wwwroot/lin-notebook-v10/data/
    chown -R 10001:10001 /www/wwwroot/lin-notebook-v10/data
    chmod 700 /www/wwwroot/lin-notebook-v10/data
    mkdir -p /www/wwwroot/lin-notebook-v10/backups
    chown 10001:10001 /www/wwwroot/lin-notebook-v10/backups
    chmod 700 /www/wwwroot/lin-notebook-v10/backups

数据库应位于 V10 的 data/space.sqlite，图片位于 data/uploads/。不能出现 data/data/。保留 V10 原始数据副本和备份，不要在唯一副本上试迁移。不要运行 docker compose down -v。

如果使用 Docker 命名卷而非绑定目录，先从 docker inspect 确认卷名，使用停机快照导出；不要猜卷名或用新空卷覆盖现有内容。

## 4. 候选验证

首选在本地用 npm run demo 验证界面，再在服务器上使用生产数据的独立副本做候选迁移。候选必须使用独立 data 目录、端口、Compose 项目和不冲突的 Docker 子网；仅修改宿主机端口而继续挂载生产 data 并不隔离。

正式生产数据已停写后，可将快照再复制一份到 data-upgrade-test/，让候选 Compose 文件挂载该副本到 /app/data。为候选设置未占用的回环端口（例如 4319），保留 APP_ENV=production，并把 FORWARDED_ALLOW_IPS 设置为候选网络的实际网关。若服务器网络网段冲突，先核对 Docker 网络再选另一个私有子网。

候选不得同时连接真实 SMTP 或运行会产生外部副作用的计划任务。将邮件密钥留空，并在副本中暂停自动化和邮件计划；不要在测试结束后把测试数据库当备份。测试副本完成 V9→V10 schema 迁移（已有 V10 不需重复迁移）、健康检查与只读检查后，确认结果，再用原始停写备份初始化正式 data/并执行正式切换。

候选配置应使用独立 Compose 项目名，例如 `lin-notebook-candidate`，而不是沿用正式的 `name: lin-notebook`。替换复制到候选中的 `data` 挂载路径、回环端口和网络子网后，再启动；否则 Compose 可能重建原生产容器。候选配置不提交真实 `.env` 或数据。正式切换同样应明确原 Compose 项目名，避免误操作其他服务。

    docker compose -f compose.candidate.yaml config --quiet
    docker compose -f compose.candidate.yaml up -d
    docker compose -f compose.candidate.yaml ps
    docker compose -f compose.candidate.yaml logs --tail=100 space
    curl -fsS -H 'Host: lolicong.xyz' http://127.0.0.1:4319/healthz
    curl -fsS -H 'Host: lolicong.xyz' http://127.0.0.1:4319/api/status

健康检查应返回 version 10.0.0，已有站点应返回 setup:false。验证旧账号能登录；确认文章、说说、相册和图片存在，私密内容未公开，草稿图片不可匿名访问。不要在测试账号中重用生产密码。

若未能安全配置隔离候选，不要在生产库上试跑：保留备份，跳过服务器候选服务，按计划停机后一次性切换并执行本节健康和内容验收。

## 5. 正式切换

1. 再次停止所有旧版写入进程，并执行一次停写完整备份。复制到服务器外部后再继续。
2. 确认新目录 data/ 从这次的生产快照恢复，不是 data/demo-v10 或测试副本。
3. 核对 .env、10001 属主、磁盘空间、镜像 ID 和代理可信地址。
4. 检查宿主机端口是否空闲。默认 Compose 绑定 127.0.0.1:4317；若端口被占用，只把 Compose 的宿主机端口改为现场确认的空闲端口，容器端口仍为 4317。
5. 执行 docker compose up -d --no-build，检查 docker compose ps、logs 和 docker compose port space 4317。
6. 用 Host: lolicong.xyz 请求 /healthz 和 /api/status。healthz 应返回 10.0.0.；api/status 应显示 setup:false、authenticated:false。
7. 更新宝塔代理目标为该宿主机端口，Nginx 必须传递 Host $host、X-Forwarded-Proto $scheme，并以 $remote_addr 覆盖 X-Forwarded-For。
8. 宝塔配置检查通过后 reload Nginx。从公网 HTTPS 无痕窗口验证首页、原账号登录、文章、图片、说说、相册、评论审核、私密内容隔离和管理页。
9. 检查日志、容器健康、磁盘和资源；确认只剩一个生产写入实例后结束维护窗口。

10. 配置建站日期、首页展示数量与公开范围；确认字体、页脚状态及关于页。需要两篇新博文时，在“功能 → JSON 导入”导入仓库 `docs/posts/v10-posts.json`，先校验并创建草稿，检查后再发布。不要用脚本覆盖已有文章。

healthz 成功不代表公网代理正确；公网 HTTPS 检查也不可省略。若出现“无效主机名”，检查 Nginx Host 是否写成了 127.0.0.1；正确值是 Host $host。

## 6. 回滚

如果切换失败，先停止 V10 写入：

    cd /www/wwwroot/lin-notebook-v10
    docker compose stop space

将宝塔 Nginx 代理恢复到记录的旧端口，再按旧部署方式启动原来的镜像/程序与旧数据。若旧版本不能读取升级后的数据库，必须恢复升级前完整数据副本；不要让旧、新进程同时写同一库。

V10 已经接收新文章、评论或图片时，先保留并备份升级后的数据。不能直接以旧快照覆盖而丢失新内容；先评估导出、合并和图片迁移，再恢复服务。回滚后检查文章、图片、登录与写入，并保留故障日志和两份数据库快照。

在确认回滚成功和数据可用之前，禁止删除旧容器、旧镜像、旧目录、备份卷或旧 .env。禁止使用 docker compose down -v。

## 验收边界

本地自动化测试、演示站和隔离数据副本不能证明真实 SMTP、服务器 Docker、宝塔代理或公网 DNS 已通过。真实邮件须用测试收件箱验证；真实容器应完成镜像健康检查、SQLite 完整性和重启持久性检查。没有执行的检查必须标记为待完成。
