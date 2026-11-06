# 部署入口

本项目当前为 V10：Vue 3 前端、FastAPI 后端、SQLite 数据库，使用 Docker 部署。新部署、宝塔配置、备份与故障排查请看 [完整部署手册](docs/DEPLOY.md)。

当前线上若仍在运行 V9，请先阅读 [V9 → V10 升级与回滚步骤](docs/V10-upgrade-and-rollback.md)。这套流程要求先备份服务器自己的数据库和图片，并使用独立目录、端口和测试数据完成候选验证。

本地功能体验请看 [V10 演示说明](docs/V10-release-and-demo.md)。演示数据库位于 `data/demo-v10`，与生产数据隔离；**不要将演示数据复制到服务器，也不要在生产目录执行 `docker compose down -v`。**

V10 镜像为 `lin-notebook:10`，健康检查版本为 `10.0.0`。宿主机端口与反向代理目标必须按部署现场核实；Nginx 应传递 `Host $host`。
