# deploy_online

Linux 主机部署管理平台。项目直接运行在宿主机普通 Linux 用户下，通过 Web 页面管理多个项目，并执行可配置的多步骤部署流程。

## 特点
- 多项目、多步骤部署
- 每个步骤独立配置工作目录、Shell、命令、超时和失败策略
- 支持 bash / zsh
- 支持 git_pull
- 支持任意命令步骤，可自行实现构建、重启、健康检查等流程
- 部署前保存完整配置快照，历史记录不受后续项目修改影响
- Git 部署记录前后 commit SHA
- 实时日志、部署历史、取消、重试
- Secret 环境变量使用应用密钥加密存储
- SQLite + WAL，适合单机部署
- Alembic 管理数据库结构，启动时自动执行 Migration
- API 与部署 Worker 分离，API 重启不会丢失 pending 部署
- 用户角色：admin / operator / viewer

## 架构
浏览器 → FastAPI API → SQLite

部署执行链：
浏览器 → 创建 Deployment(pending) → SQLite → Worker → Shell → 日志/状态写回 SQLite

API 服务和 Worker 是两个独立 systemd 服务。Worker 负责实际执行部署任务，因此不应该使用多个 Worker 实例。

## 部署
### 1. 配置
cp backend/.env.example backend/.env
至少修改 SECRET_KEY、ADMIN_USERNAME、ADMIN_PASSWORD。
首次启动且数据库没有用户时，会创建管理员账号。

### 2. 安装依赖
cd backend
uv sync

数据库 Migration 会在 API 和 Worker 启动时自动执行。新数据库会从 `0001_initial` 创建；已经由旧版本 `create_all()` 创建的完整数据库会自动标记为当前 Migration 基线，后续结构变更通过新的 Alembic revision 执行。

### 3. 启动 API
systemctl --user enable --now deploy_online.service
API 默认监听 http://127.0.0.1:8000。

### 4. 启动 Worker
systemctl --user enable --now deploy_online-worker.service
查看状态：systemctl --user status deploy_online.service
systemctl --user status deploy_online-worker.service
查看日志：journalctl --user -u deploy_online-worker.service -f

## 部署步骤
常用步骤类型：
- command：执行任意 Shell 命令
- git_pull：执行 git checkout <branch> && git pull --ff-only
- health_check：可使用命令步骤实现，例如 curl 本机健康接口
部署命令以配置的项目 Shell 登录方式运行：bash 使用 /bin/bash -lic，zsh 使用 /bin/zsh -lic。
因此可以复用用户自己的 Shell 环境，例如通过 asdf 管理的 Node.js。

## 安全模型
部署命令本质上是以运行 deploy_online 的 Linux 用户身份执行任意 Shell 命令。
因此不应将服务暴露给不可信用户；operator 也拥有执行项目命令的能力；viewer 只能查看。
Secret 环境变量存储在数据库中时会加密。HTTP API 和 WebSocket 都要求登录。

## 数据
默认 SQLite：backend/data/deploy_online.db
部署记录保存操作用户、项目、时间、exit code、配置快照、备注、Git 前后 commit SHA、retry 来源和每一步日志。
SQLite 使用 WAL 模式和连接超时，降低 API 与 Worker 同时访问数据库时的锁冲突。

## 开发
后端：cd backend && uv run uvicorn app:app --reload
Worker：cd backend && uv run python worker.py
数据库迁移：cd backend && uv run alembic upgrade head
测试：cd backend && uv run pytest
前端：cd frontend && npm install && npm run dev
生产环境建议使用 systemd 管理 API 和 Worker，不建议让 uvicorn 进程直接承担部署任务。