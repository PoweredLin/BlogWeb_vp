# V9 架构与开发

## 运行结构

浏览器 → 宝塔 Nginx HTTPS → `127.0.0.1:4317` → FastAPI/Uvicorn → SQLite 与上传目录。

单个 Python 服务处理 API 和构建后的静态文件。Node 只用于构建及部分回归测试，运行容器不启动 Node、Express、Redis 或 MySQL。适合现有 2 核 4G 服务器。

| 路径 | 职责 |
|---|---|
| `backend/main.py` | 应用工厂、安全边界、静态白名单、页面/旧地址分发、RSS、SEO |
| `backend/api.py` | 原有 `/api` 接口，创作、账号、审核、生活记录 |
| `backend/storage.py` | SQLite、事务、增量迁移、迁移前安全副本 |
| `backend/validation.py` | 原接口字段、跨字段校验、设置模型 |
| `backend/content.py` | Markdown、文章、版本冲突、专注、角色互动 |
| `backend/security.py` | scrypt、会话、频率限制、验证码、图片验证 |
| `backend/git_activity.py` | 外部动态的后台同步、缓存和退避 |
| `backend/backups.py` / `cli.py` | 兼容个人 JSON 备份、完整备份、站主初始化/重置 |
| `source/blog` | Vue 3 博客，保留二次开发后的视觉和交互 |
| `source/admin` | Vue 3 个人空间与管理外壳 |
| `source/tools` | Vue 3 生活工具渲染、原工具模板和操作逻辑 |
| `public/assets` / `audio` | 站点预设图片与主动播放语音 |
| `tests` | Python 安全/迁移/缓存测试及浏览器、API 兼容回归 |

生活工具仍通过同源 iframe 与主界面隔离 CSS，跨窗口消息校验来源和发送窗口。工具内部现在由 Vue 渲染器生成和更新 VNode，现有视图函数与委托事件继续复用；并非把每个旧模板都重写为 `.vue` 单文件组件。这样保留既有交互及样式，后续可按工具逐步拆组件。

## 数据兼容

SQLite 仍使用 V8 的表、JSON 字段和上传文件名。V9 增加 Git 缓存表、文章链接索引，将 `user_version` 升至 9。已有数据首次启动前自动保存 `data/migration-safety/before-v9.sqlite`。迁移不会插入演示文章，也不会替换站主账号。

密码保留 Node scrypt 参数 `N=16384,r=8,p=1,dklen=64`，盐按文本使用；旧的短密码仍可验证，新密码要求至少 10 字符。会话仍为 HttpOnly/SameSite=Strict Cookie，数据库只存令牌哈希。上线后建议通过界面换掉历史弱密码。

`backend/contracts/v8.json` 是从旧 Zod 模型导出的接口契约与测试演示数据，运行时由 Python 校验，并补充日期、睡眠分期、收藏进度等跨字段约束。新功能应同时修改契约/校验与测试。

## 性能边界

- SQLite WAL、5 秒 busy timeout，写操作使用短事务；默认一个 Uvicorn 进程。
- Uvicorn 并发上限 32、空闲连接超时 5 秒；默认不逐条打印访问日志，由 Nginx 记录访问，应用保留错误日志。
- 按 slug 查询单篇文章，不扫描全部文章；公开列表只查询可公开状态，并按作者复用资料查询。
- Markdown 使用有界 LRU 缓存；仅缓存渲染结果，读取权限仍每次判断。
- 静态 hash 文件缓存一年；HTML/API 不缓存；图片公开状态仍由后端判断。
- 启用 gzip，文章、管理、生活工具分开构建和加载。
- Git 请求不占用页面响应等待时间，离线仍可使用已有内容。
- 请求体最大 12MiB，单图 8MiB、2400 万像素、最长边 12000；上传有 30 秒读取期限。
- Compose 限制 768MiB 内存、1.5 CPU、128 个进程。构建阶段不受这个运行限额约束，建议本地构建镜像后上传服务器。

公开列表保留原版全文搜索所需 `searchText`，文章数量很大时响应体也会增大。若以后达到数千篇，应将搜索分页移到后端，不能仅靠增加内存解决。

## 本地开发

安装 Python 3.13、Node 24.9+，在项目根目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
npm ci
npm run build
# 开发环境不要设置 APP_ENV=production；不要直接用线上 data 做测试
$env:APP_ENV='development'
$env:COOKIE_SECURE='false'
npm start
```

Linux 的 Python 路径为 `.venv/bin/python`。Windows 如 npm 被其他工具覆盖，可用 `node <Node安装目录>/node_modules/npm/bin/npm-cli.js` 代替 `npm`。

测试使用独立临时数据目录。浏览器测试要求 Chromium，可执行 `npx playwright install chromium` 并设置 `CHROME_PATH` 指向安装后的浏览器可执行文件。

```sh
npm test
npm run test:browser
npm run test:appearance
python -m scripts.benchmark
```

更新 Python 依赖后运行 `python scripts/lock-python.py` 生成运行依赖锁；Docker 安装 `backend/requirements.lock.txt`。更新 npm 依赖必须提交 `package-lock.json` 并重新构建、回归。
