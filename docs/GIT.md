# BlogWeb_vp 的 Git 使用说明

本文对应当前项目，命令在项目根目录执行。Git 负责代码版本；服务器上的文章、账号和上传图片需要单独备份。

## 1. 当前仓库

| 项目 | 当前设置 |
| --- | --- |
| GitHub | https://github.com/PoweredLin/BlogWeb_vp |
| 克隆地址 | `https://github.com/PoweredLin/BlogWeb_vp.git` |
| 主分支 | `main` |
| 默认远程 | `origin`，指向 GitHub |
| 旧远程 | `gitee`，保留原地址作为记录，不会随 GitHub 推送自动同步 |
| 本机目录 | `C:\Users\JLZ\Documents\ChatGPT\个人博客+工作台` |

在 PowerShell 中进入目录并检查：

```powershell
cd 'C:\Users\JLZ\Documents\ChatGPT\个人博客+工作台'
git status
git branch --show-current
git remote -v
```

日常使用 `main`，不用重新运行 `git init`，也不用再次克隆到现有项目目录。

## 2. 登录与提交身份

这台电脑已经使用 Git Credential Manager 登录 GitHub。换电脑或授权失效时：

```powershell
git credential-manager github login --username PoweredLin --browser
```

在浏览器完成授权。不要把密码或访问令牌写进源码、远程 URL、文档或聊天。

Git 的提交作者与 GitHub 登录账号是两件事。本地此前 AI 辅助提交使用 `Codex <codex@localhost>`；不会因登录你的账号而自动改写旧提交。你自己开始提交前，可在本仓库设置：

```powershell
git config --local user.name 'PoweredLin'
git config --local user.email '152774884+PoweredLin@users.noreply.github.com'
```

这个隐私邮箱来自你在 GitHub 仓库中的初始提交；以后若修改 GitHub 邮箱设置，以 GitHub Settings → Emails 中显示的地址为准。只影响之后的新提交，不改写历史。

## 3. 日常修改与上传

开始修改前，工作区没有未提交改动时：

```powershell
git switch main
git pull --ff-only origin main
```

修改后先检查实际变化：

```powershell
git status --short
git diff
```

改动代码时，按涉及功能进行验证，例如：

```powershell
npm run build
npm test
# 改动页面和交互时，再按架构文档配置浏览器并执行
npm run test:browser
```

仅修改说明文档时，检查内容、路径和链接即可，不必运行整套程序测试。

确认改动和待上传文件后：

```powershell
git add README.md docs/GIT.md
git diff --cached --stat
git diff --cached
git diff --cached --check
git commit -m 'docs: 更新 Git 使用说明'
git push origin main
```

把 `git add` 后面的路径换成实际改过的文件。确认所有变化都属于本次工作时也可以使用 `git add -A`，随后仍要检查暂存内容。

`commit` 保存到本地历史，`push` 才上传到 GitHub。推送后运行 `git status` 应显示工作区干净、分支与远程同步；也可在 GitHub 查看最新提交。

## 4. 换电脑或下载项目

在一个准备存放项目的父目录执行：

```powershell
git clone --branch main https://github.com/PoweredLin/BlogWeb_vp.git
cd BlogWeb_vp
```

新克隆没有依赖、构建产物、真实 `.env` 或线上数据库。按 [架构与本地开发](ARCHITECTURE.md) 安装依赖并构建；按 [部署文档](DEPLOY.md) 迁移服务器数据。

GitHub 网页也可以通过 Code → Download ZIP 下载代码，但 ZIP 不带 `.git` 历史，不适合继续提交和推送。

## 5. 服务器更新

只有从 Git 克隆的部署目录才能直接拉取：

```sh
git status --short
git pull --ff-only origin main
docker compose build
```

确认构建成功，按部署文档停写、做全站备份，再替换容器：

```sh
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=100 space
curl -fsS http://127.0.0.1:4317/healthz
```

`git pull` 只更新代码，不代表数据库已备份，也不会自动重新构建或重启容器。服务器性能有限时，可以在本机构建镜像再 `docker save/load`，详细操作见 [部署文档](DEPLOY.md)。

线上已经有文章和图片时，必须保留服务器的 `data/`，不能拿本地 `data/` 覆盖。

## 6. 哪些文件不会上传

项目 `.gitignore` 已排除：

- `.env` 等真实配置；只提交不含秘密的 `.env.example`。
- `data/`：数据库、账号、文章、上传图片及私有内容。
- `backups/`：完整备份及历史安全副本。
- `node_modules/`、`.venv/`：可重新安装的依赖。
- `test-results/`、日志、Python 缓存。
- 三套生成的前端目录：`public/blog-app/`、`public/admin-app/`、`public/tools-app/`。
- ZIP、Docker 导出 TAR，以及本地素材来源路径清单。

`public/assets/` 等预设素材属于代码发布内容，会上传仓库；用户上传的图片在 `data/uploads/`，不会上传。

检查排除规则，例如：

```powershell
git check-ignore -v .env data/space.sqlite lin-notebook-v10.tar
git ls-files data backups .env
```

第二条正常应无输出。`.gitignore` 对已被跟踪的文件不自动生效；如果秘密曾被提交，删除文件或补忽略规则不能清除历史暴露，应先撤销/更换秘密，再处理历史。

## 7. 查看记录与撤销

```powershell
git log --oneline -10
git show --stat HEAD
git diff
```

只是误暂存文件、想保留本地修改：

```powershell
git restore --staged docs/GIT.md
```

已经提交、尤其已经推送的改动，推荐通过 `git revert` 创建反向提交。先从日志找到要撤销的提交，检查内容，再执行（替换占位符）：

```powershell
git revert <要撤销的提交编号>
git push origin main
```

反向提交可能产生冲突，解决后按 Git 提示继续；决定取消时可执行 `git revert --abort`。不要用 `push --force` 覆盖远程历史，也不要随手运行 `reset --hard` 或 `clean -fdx`，后者可能删除被忽略的本地数据。

代码回退不等于数据回退。涉及数据库版本变化时，按照部署文档使用对应时间点的数据备份与旧镜像。

## 8. 常见问题

### 推送提示 non-fast-forward

远程有本地没有的提交。先保存本地改动，执行 `git fetch origin` 和 `git log --oneline --graph --all -15` 查看分歧。不要强推。若只有远程前进，使用 `git pull --ff-only origin main`；若双方都有新提交，需要先合并并解决冲突，再测试和推送。

### 拉取提示本地修改会被覆盖

先用 `git status`、`git diff` 看清变化，完成本地提交后再拉取。不要为了拉取直接删除改动，也不要把真实配置或数据库加入提交。

### Windows 提示 unable to get local issuer certificate

本机曾遇到 Git 自带证书库无法验证证书的问题，使用 Windows 系统证书库后连接成功。可以对当前命令指定：

```powershell
git -c http.sslVerify=true -c http.sslBackend=schannel push origin main
```

如果希望仅在本仓库持续使用该设置：

```powershell
git config --local http.sslBackend schannel
git config --local http.sslVerify true
```

`schannel` 适用于 Windows，不要照搬到 Linux 服务器。不要设置 `sslVerify=false`。

### GitHub 网页贡献者与 README 不一样

GitHub Contributors 根据默认分支的提交历史及邮箱关联生成；[贡献者说明](../CONTRIBUTORS.md) 还说明维护工作、上游来源与 AI 工具参与范围。修改这份说明不会给任何人添加写入权限，也不会自动改变历史提交作者。
