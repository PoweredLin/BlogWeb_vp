# 前端接口基础与本轮功能整理

本轮目标是补齐功能连接、明确公开和私有边界，为后续 Claude 重做视觉提供可直接调用的接口。没有引入低代码脚本、任意插件执行或额外数据库服务。旧接口保持兼容；现有服务器升级不需要重建数据。

## 入口与职责

- 公开博客：文章、说说、相册、季度海报墙和被站主明确公开的书签。
- 我的房间：私人展示和兴趣内容。
- 功能工具箱：自动化、邮件、文档、开发书架、JSON 导入、API 接入说明。
- 管理：公开内容、页面和片头、账号审核、评论审核、访问凭证。

管理概览改为单次 `/api/private/overview` 请求，显示文章/草稿数、私有文档数、评论/注册待审核数、运行待确认数和邮件配置状态。邮件状态只表示配置条件，不保证外部 SMTP 投递成功。

## 新读接口

所有分页接口返回 `{items,total,page,pageSize,hasMore}`。page 从 1 开始；pageSize 默认 24（文章默认 12，运行默认 20），最大 100。不合法的参数返回 400。搜索为不区分大小写的子串搜索，中文可正常使用。

| 方法与地址 | 参数 / 返回 | 访问范围 |
| --- | --- | --- |
| GET `/api/public/bootstrap` | apiVersion、site、layout（不含 room）、intro、featuredPosts（最多 12 篇元数据）、navigation | 公开 |
| GET `/api/public/home` | accent、按配置顺序的 modules；每项含 id、data | 公开 |
| GET `/api/public/status` | ok、version、siteStartedAt、checkedAt；检查应用与数据库，建站日期可为空 | 公开 |
| GET `/api/public/catalog/posts` | q、category、tag、page、pageSize；文章元数据，无正文 | 公开 |
| GET `/api/public/catalog/anime` | season（如 2026-Q4）、q、weekday（一至日 / unknown）、page、pageSize；另含 seasons | 公开 |
| GET `/api/private/overview` | content、review、automation、mail、recent | 管理员 |
| GET `/api/private/catalog/records/{kind}` | q（标题）、subtype、season（all / 季度 / 空值待整理）、page、pageSize；另含 seasons | 管理员 |
| GET `/api/private/catalog/documents` | q（标题和正文）、category、page、pageSize；摘要和 categories，无完整正文 | 管理员 |
| GET `/api/private/documents/{id}` | 文档全文与 version | 管理员 |
| GET `/api/private/media` | source（all / uploads / assets）、q（文件名）、page、pageSize | 管理员 |
| GET `/api/private/automation?compact=true` | 模板、任务、最近 50 条运行摘要 | 管理员 |
| GET `/api/private/automation/runs` | state、flowId、page、pageSize | 管理员 |
| GET `/api/private/automation/runs/{id}` | 单次运行的 snapshot、result、状态和错误 | 管理员 |
| GET `/api/private/api-contract` | OpenAPI、recordSchemas、conventions，不含运行凭证 | 管理员 |

完整契约可在“功能 → API 接入”下载 JSON。开发模式仍可使用 `/api/docs`；生产不开放匿名接口文档。旧接口中的字典请求体没有全部转换为 Pydantic 字段，因此 OpenAPI 并不包含所有旧请求字段的详细约束；记录字段以下载 JSON 的 `recordSchemas` 和 `backend/contracts/v8.json` 为准。

### 首页模块数据

- articles：分页文章元数据，现有首页文章组件仍可独立分页。
- anime：分页海报数据及实际 season。
- web：明确公开的书签 items、选中的 selected（无公开书签时为 null）。只有 `embeddable=true` 才显示 iframe，其他链接直接外部打开。
- profile：仅 name、tagline、bio。
- moments / albums：最近 3 条已公开内容。images 可能是旧字符串或 `{url,caption}`，展示层兼容两种形式。

书签默认私有。先在“功能 → 开发书架 → 整理书架”勾选“允许首页公开”，再在“管理 → 页面与片头”选择首页书签。外站可以通过响应头拒绝 iframe；本系统不会代理外站或绕过来源限制。

### 布局新字段

沿用 GET/PUT `/api/private/page-layout` 和 version 并发保护：

```json
{"animeSeason":"auto","animeLimit":8,"webDocumentId":"","animeAutoPublic":true}
```

auto 按上海时区选择当前季度；数量限制 1–24；文档空值选择第一个公开书签。自动公开仅作用于已确认采集并关联的番剧元数据，手动私人收藏不会自动公开。关闭总开关后仍单独公开的作品继续展示。管理海报墙会显示 effectivePublic，并区分“单独公开”开关。

### 素材与片头

素材接口返回 url、name、source、bytes、public。仅查询素材不会公开图片。上传图被选入 `introPhotos` 并保存后才用于公开片头，最多 18 张，支持排序和移除。素材库支持文件名搜索、继续加载；番剧收藏的图片仍可选。

`public=true` 表示当前可匿名访问，不代表用户点过某个公开按钮。不要新增一个前端按钮就直接改上传归属或复制文件到静态目录。

### 自动化性能

列表 SQL 不读取 result JSON。当前界面每 5 秒在可见状态下读取摘要；只有所选运行状态或 updated 变化时读取详情。复杂本地 AI 工作继续通过以下接口提交，不在 2 核 4 GB 云主机执行浏览器爬虫或大模型：

```http
POST /api/v1/automation/results
Authorization: Bearer <仅本地保存的访问凭证>
Idempotency-Key: <一次提交一个稳定的唯一键>
Content-Type: application/json

{"flowId":"本地资料任务 ID","title":"资料标题","content":"Markdown 正文"}
```

凭证需要 automation:submit 权限。同键相同内容不重复创建，同键不同内容返回 409。结果等待站主确认，不直接公开文章。发布、JSON 导入等继续使用现有有作用域的 API，详见项目功能文档与接入脚本 `scripts/local-ai-submit.py`。

## Claude 前端交接提示词

请基于现有 Vue 3 页面改视觉，不改变公开/管理员边界。公开首页要有桌面网站的信息层级、留白和个性，而非大量相同圆角卡片。私人房间可更有宅文化的收藏陈列，简约工作室则强调编辑效率；两套主题使用相同业务接口，改变构图、排版和背景层次。保持移动端可用及 reduced-motion。

优先使用本文件的新分页和聚合接口，不读取 `/api/private/state` 来绘制单个模块，不用 `/api/public` 获取所有文章正文来实现卡片列表。每个页面必须设计加载、空数据、失败重试、无权限、保存中、成功和 409 冲突状态。切换查询要取消旧请求或忽略旧响应。不得把 Bearer Token、SMTP 凭证或数据库内容放入浏览器构建产物。

片头先覆盖加载底色，然后用照片拼出可配置名称，再衔接轮播首页；素材来自 bootstrap.intro.photos，不另造一套配置。提供跳过、重播与减少动画模式。文章上传使用服务端 URL 并等待图片解码，保留上传和加载反馈。

### 源码与素材位置

- `backend/experience.py`：新接口与公开投影。
- `backend/page_layout.py`：首页/房间/片头配置及版本保护。
- `backend/reference_docs.py`：书签、公开范围和 iframe 来源白名单。
- `source/shared/frontend-api.ts`：分页、素材、文档和运行摘要类型与请求辅助函数。
- `source/blog/src/integration/LinHero.vue`、`LinFrameIntro.vue`：首页与拼字动画。
- `source/blog/src/integration/LinHomeModules.vue`、`LinAnimeWall.vue`：首页模块和公开海报墙。
- `source/admin/src/integration/LinPageLayout.vue`：布局和素材选择器。
- `source/admin/src/integration/LinManagement.vue`、`LinApiReference.vue`：管理/功能入口和接口说明。
- `public/assets/` → `/assets/<文件名>`：内置公开图片。
- 运行数据目录下 `uploads/` → `/uploads/<服务端文件名>`：上传与采集封面，按公开引用/归属鉴权。
- `public/blog-app/`、`public/admin-app/`、`public/tools-app/`：构建生成物，只通过 `node scripts/build.mjs` 更新，不直接编辑。

## 升级与验证

本轮无需 SQL 结构迁移，也不删除任何线上文章、图片、配置或运行历史。缺失布局字段按默认值补全。升级前按现有部署文档备份数据库和 uploads，更新源码并重新构建 Docker 镜像、重建服务；必须继续挂载原数据卷并保留 `.env` 和 EMAIL_ENCRYPTION_KEY。不要把本地 demo 数据覆盖线上。

检查 `/healthz`、管理员登录、首页模块、海报分页、布局保存、书签公开及自动化详情。回退时恢复旧镜像和升级前备份，操作细节见 `docs/V10-upgrade-and-rollback.md`。本轮代码未替你部署到云端。

当前边界：素材接口仍扫描个人上传目录和内置图片；数量特别大时应进一步改用索引表。番剧星期按来源提供的中文播出说明解析，没有说明的归入待定，不承诺实时更新到具体集数。SQLite 适合目前个人站点，不是多实例并行写入方案。真实 SMTP、外站 iframe 可用性和 Yuciwiki 当前内容仍受外部服务影响。
