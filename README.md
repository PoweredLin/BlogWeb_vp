# Lin 的随手记 · V9

Vue 3 博客、个人空间与创作管理，FastAPI + SQLite 后端，Docker 部署。保留 V8 的两套空间主题、博客布局、生活记录与创作功能，兼容已有数据库及上传图片。

仓库：<https://github.com/PoweredLin/BlogWeb_vp>

面向个人使用的精致博客与私人工作台：文章、说说、相册、评论审核、双主题空间、生活记录和 Git 动态集中管理，支持 Docker 部署与旧版数据迁移。

## 维护者与贡献来源

- [Lin / PoweredLin](https://github.com/PoweredLin)：项目维护、需求与视觉方向、素材整理、部署与使用反馈。
- Mr Zhang 与 PureAdmin：原博客、后台界面和基础组件来源，原许可证继续保留。
- Codex、WorkBuddy：开发过程中的 AI 辅助工具；具体参与范围见 [贡献者与来源说明](CONTRIBUTORS.md)。

## 文档

- [部署、宝塔配置、V8 数据迁移、备份与回滚](docs/DEPLOY.md)
- [功能与角色权限](docs/FEATURES.md)
- [架构、本地开发和性能边界](docs/ARCHITECTURE.md)
- [安全测试与验证记录](docs/SECURITY.md)
- [素材来源和许可证](ASSETS.md)

## 本地启动

```sh
python -m venv .venv
# Windows；Linux 使用 .venv/bin/python
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
npm ci
npm run build
npm run owner:init
npm start
```

访问 <http://127.0.0.1:4317>。已有 `data/space.sqlite` 时跳过初始化。没有通用默认密码；忘记密码使用 `npm run owner:reset`。

`.env.example` 用于生产部署，本地 HTTP 开发不要开启 production/Secure Cookie。真实 `.env`、数据、上传图片及备份不提交仓库。

## Docker

```sh
cp .env.example .env
# 修改 SITE_URL，迁移线上 data，设置目录权限；详见部署文档
docker compose build
docker compose up -d
```

运行仅需 Python 容器；Node 仅用于构建。宿主机端口只监听 `127.0.0.1:4317`，通过宝塔 HTTPS 反向代理对外提供服务。

**线上已写的文章和上传的图片必须从服务器迁移，不能用本地 data 覆盖。**

## 验证

```sh
npm test
npm run test:browser
npm run test:appearance
```

浏览器测试需配置 `CHROME_PATH`。测试使用临时数据库，不修改真实内容。

原博客与后台的源码许可证保留在 `source/` 和 `public/licenses/`。来源与致谢保留在网站“关于”页。

本仓库保留维护者选用的 Apache 2.0 根许可证；第三方源码遵循其原有 MIT 许可证，图片、语音等素材不包含在代码许可授权中，详见 [ASSETS.md](ASSETS.md)。
