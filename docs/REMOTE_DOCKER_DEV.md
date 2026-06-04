# 远程 Docker 开发部署

## 目标

在远程机器 `<REMOTE_HOST>` 上保留完整源码，并用 Docker Compose 启动服务：

- 后端：`http://<REMOTE_HOST>:8000`
- 前端：`http://<REMOTE_HOST>:5173`

Compose 使用源码目录 bind mount。远程二次开发时，修改源码后：

- 前端 Vite 通常会热更新。
- 后端 FastAPI 使用 `uvicorn --reload`，Python 文件修改后会自动重载。
- 依赖或环境变量变化后执行 `docker compose -f docker-compose.dev.yml restart`。

## macOS 远程机运行时

远程机器是 macOS Intel。推荐使用 Homebrew + Colima：

```bash
brew install docker docker-compose colima
colima start --cpu 2 --memory 4 --disk 40
docker version
docker compose version
```

## 首次启动

```bash
cd ~/Poly_Codex
cp backend/.env.docker.example backend/.env.docker
cp frontend/.env.docker.example frontend/.env.docker
docker compose -f docker-compose.dev.yml up -d --build
```

## 常用命令

查看服务：

```bash
docker compose -f docker-compose.dev.yml ps
```

查看日志：

```bash
docker compose -f docker-compose.dev.yml logs -f backend
docker compose -f docker-compose.dev.yml logs -f frontend
```

重启：

```bash
docker compose -f docker-compose.dev.yml restart
```

停止：

```bash
docker compose -f docker-compose.dev.yml down
```

更新依赖后重建：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

## 注意

1. 这套 Compose 是远程开发模式，不是公网生产模式。
2. 当前系统没有登录鉴权，不建议直接暴露到公网。
3. 如果只想停止扫描流量，不需要停容器，可以在前端点“暂停扫描”。
