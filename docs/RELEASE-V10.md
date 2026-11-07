# 林间笔记 V10：上传与部署准备

2026-11-07 后台加载补丁：修复管理静态资源被误设为 no-store、资源并发超过 Uvicorn 32 连接上限的问题，增加静态文件免会话查询、128 并发上限及 2 秒 keep-alive。后台禁用 HTML modulepreload；路由仍按需加载。38 项后端测试、64 并发两轮资源测试、后台浏览器专项通过。构建完成。容器重复创建、端口和补丁升级步骤见 [后台 503 与容器排查](后台503与容器排查.md)。不需要再次迁移数据库。

本次交付保留 Claude 完成的页面设计，统一 Lin 标识、补充侧栏建站时长与页脚真实服务状态、弱化滚动文字条背景，更新关于页，并增加本地字体。不是线上发布记录；测试结果见文末。

发布收尾：移除“最近的片刻”“光影收藏”标题末尾句号；新增两篇可导入草稿的博文。导入包已在隔离数据库验证：创建两篇私人草稿、公开文章列表仍为空、重复导入被拒绝。没有对线上内容执行导入。

## Git 上传

目标仓库为 `https://github.com/PoweredLin/BlogWeb_vp.git`，主分支 `main`。本次发布包含此前 V10 的功能、API 与 Claude 视觉修改，以及本轮文字和升级文档整理。发布后以 GitHub main 的提交记录和本地 `git log -1` 对照确认代码版本；本说明不代表已经升级云端。

在项目根目录执行，先审阅，再上传：

```powershell
git branch --show-current
git remote -v
git status --short
git diff --check
git add -A
git diff --cached --stat
git diff --cached --check
git diff --cached --name-only
git commit -m 'feat: 完善林间笔记 V10 与发布文档'
git push origin main
```

暂存清单不应包含 `.env`、data、backups、上传图、数据库、日志或本地测试截图。`.gitignore` 已排除这些目录；`public/fonts/` 是正式发布资源，必须提交，包含字体、许可及 manifest。构建结果目录由 Docker 构建生成，不提交。不要删除图标字体，它仍支持旧组件。

## 生产升级顺序

从 V9 升级时，优先按 [V9 → V10 完整升级与回滚](V10-upgrade-and-rollback.md) 在新目录操作；以下原地更新命令仅适用于熟悉当前挂载、已留存旧镜像及原配置的维护场景。服务器曾使用 4318，原端口与反向代理设置不要因拉取默认 Compose 而被静默替换。

1. 记录当前镜像标签、容器挂载路径、端口及反向代理目标。备份 `.env`，保留 `EMAIL_ENCRYPTION_KEY`；密钥丢失会使已存邮箱密码无法解密。
2. 先用线上数据副本在隔离目录测试。不要将本地 `data/demo-v10` 传到服务器覆盖正式数据。
3. 进入当前正式项目目录，拉取已经审阅的代码；如有服务器本地改动，先保存差异，不直接覆盖。
4. 构建新镜像；旧服务仍可运行。生产数据目录必须继续挂载到 `/app/data`，账户、文章和 uploads 要一起保留。
5. 停写并做一致性备份，再重建容器，检查健康和页面。数据库升级与恢复细节见 [升级与回滚](V10-upgrade-and-rollback.md)。

```bash
cd /www/wwwroot/lin-notebook-v9
# 先备份原 Compose/.env 并给旧镜像保留标签，确认工作区没有未保存改动
git pull --ff-only origin main
docker compose build --pull space
# 此时停止写入，按升级文档备份数据库与 uploads
docker compose up -d --no-build space
docker compose ps
docker compose port space 4317
docker compose logs --tail=60 space
```

以上目录沿用之前服务器的名称；以实际正在使用的 Compose 目录为准。输出端口若是 4318，下面 curl 也用 4318，Nginx 必须指向同一个端口。不要只看到容器 healthy 就认为域名已经切换。

```bash
curl -i -H 'Host: lolicong.xyz' http://127.0.0.1:4317/healthz
curl -H 'Host: lolicong.xyz' http://127.0.0.1:4317/api/public/status
ss -ltnp 'sport = :4317'
```

默认 Compose 将 `127.0.0.1:4317` 映射到容器 4317。若旧 Node 仍占用该端口，先确认其身份并使用原有服务管理方式停止旧服务；不要盲目杀死其他进程。需要保留 4318 映射时，沿用服务器原有端口配置，检查 `docker compose port space 4317` 后再调整 Nginx。

宝塔反向代理关键配置：

```nginx
location / {
    proxy_pass http://127.0.0.1:4317;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 12m;
    proxy_read_timeout 60s;
}
```

`SITE_URL` 必须与实际域名和协议一致；不要把 Host 固定成 `127.0.0.1`。完成后检查 `nginx -t`，再通过宝塔重载。既有站点配置只修改对应代理段，保留 HTTPS 配置。

## 上线后设置与验收

- 管理 → 博客设置 → 基本信息：填写真实建站时间，例如 `2026-09-14T00:00:00+08:00`。示例不是已确认的上线日期，留空时显示“建站日期待设置”。修改后刷新页面。该时长表示距建站时间的日历时长，不承诺零停机。
- 首页、文章、关于、番剧、管理员登录和封面上传正常；当季内容足够时首页显示 10 部，具体数量仍可在页面布局中编辑。
- `/healthz` 返回 FastAPI JSON；`/api/public/status` 返回 ok、版本和建站时间，不应出现 Node 的 Cannot GET。
- 页脚“服务正常”表示最近一次应用与数据库连通检查成功，无法访问时显示“暂时无法确认服务状态”；不代表邮件、外站或自动化来源全部正常。
- `/fonts/inter-latin.woff2`、`/fonts/lora-latin.woff2` 返回 200；浏览器字体加载不请求 Google/CDN。
- 未登录时无法访问私人接口；已有文章、图片、评论及任务仍在；真实 SMTP 投递单独验收。

新增的两篇博文正文和草稿导入包见 [博文目录](posts/README.md)，不会随部署自动发布。

构建失败或业务异常时，按升级文档恢复之前镜像及必要的数据快照。不要 `docker compose down -v`。完整宝塔操作见 [部署文档](DEPLOY.md)。

## 本轮验证

2026-11-06 本地验证：37 项 Python 后端测试、17 项 Node 兼容与权限测试通过（含建站日期校验、公开状态字段、字体资源与许可入口）；前端完整构建成功；番剧/任务/片头浏览器专项通过；本轮页面专项覆盖状态去重与失败提示、运行时间计算、本地字体、Lin 图标、10 部番剧、两种主题和明暗模式、手机无横向溢出、关于与许可入口。`git diff --check` 与 `docker compose config --quiet` 通过。383 份候选文本文件的常见 GitHub 凭证和私钥格式扫描未命中，不代表完整的安全审计。

主要复验命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_backend.py -q
node --test tests/compat-v9.test.mjs tests/owner-v9.test.mjs
node tests/site-status.mjs
node tests/anime-wall.mjs
npm run build
docker compose config --quiet
```

浏览器测试默认使用本机已安装的测试 Chrome；换机器时可参考 `tests/anime-wall.mjs` 的 `CHROME_PATH` 配置。新状态测试使用临时数据目录和 4352 端口，不修改本地演示或线上数据。

Docker CLI 已安装，但本机 Docker Desktop Linux Engine 当前未启动，未完成镜像构建或容器运行验收。生产服务器和真实邮件投递未在本轮操作；真实邮件投递不以配置齐全代替验收。
