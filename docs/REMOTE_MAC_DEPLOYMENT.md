# 远程 Mac 部署说明

## 当前远程机器

- 地址：`<REMOTE_HOST>`
- 用户：`<REMOTE_USER>`
- 项目目录：`~/Poly_Codex`
- 后端：`http://<REMOTE_HOST>:8000`
- 前端：`http://<REMOTE_HOST>:5173`

## 当前实际部署形态

远程机器是 macOS 12 Intel。Docker CLI、Docker Compose、Colima 已安装，但 Colima 默认需要 QEMU；QEMU 在该机器上需要大量 Homebrew 源码编译，安装成本过高。因此当前先采用原生常驻部署：

- 后端：Python venv + FastAPI/Uvicorn
- 前端：Node 20 二进制 + Vite dev server
- 常驻：launchd

Docker 开发配置仍保留在项目中：

- `docker-compose.dev.yml`
- `backend/Dockerfile.dev`
- `frontend/Dockerfile.dev`
- `backend/.env.docker`
- `frontend/.env.docker`

后续如果 Docker 运行时可用，可以直接在 `~/Poly_Codex` 执行：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

## 常用远程命令

登录：

```bash
ssh <REMOTE_USER>@<REMOTE_HOST>
```

查看服务：

```bash
launchctl print gui/$(id -u)/com.polymonitor.remote.backend
launchctl print gui/$(id -u)/com.polymonitor.remote.frontend
```

重启服务：

```bash
launchctl kickstart -k gui/$(id -u)/com.polymonitor.remote.backend
launchctl kickstart -k gui/$(id -u)/com.polymonitor.remote.frontend
```

停止服务：

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.polymonitor.remote.backend.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.polymonitor.remote.frontend.plist
```

重新加载服务：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.polymonitor.remote.backend.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.polymonitor.remote.frontend.plist
```

查看日志：

```bash
tail -f ~/Poly_Codex/logs/remote-backend.out.log
tail -f ~/Poly_Codex/logs/remote-backend.err.log
tail -f ~/Poly_Codex/logs/remote-frontend.out.log
tail -f ~/Poly_Codex/logs/remote-frontend.err.log
```

## 远程二次开发

从本地同步代码到远程时，使用项目脚本，避免覆盖远程 `.env`：

```bash
POLY_REMOTE=<REMOTE_USER>@<REMOTE_HOST> ./scripts/sync_remote.sh
```

后端源码修改后：

```bash
cd ~/Poly_Codex
backend/.venv/bin/python -m compileall backend/app
launchctl kickstart -k gui/$(id -u)/com.polymonitor.remote.backend
```

前端源码修改后，Vite 通常会自动热更新。如需重启：

```bash
launchctl kickstart -k gui/$(id -u)/com.polymonitor.remote.frontend
```

如果前端依赖变化：

```bash
export PATH="$HOME/.local/node-v20.19.0-darwin-x64/bin:$PATH"
cd ~/Poly_Codex/frontend
npm ci
launchctl kickstart -k gui/$(id -u)/com.polymonitor.remote.frontend
```

## 健康检查

```bash
curl http://<REMOTE_HOST>:8000/api/health
curl http://<REMOTE_HOST>:8000/api/status
curl http://<REMOTE_HOST>:8000/api/markets
curl -I http://<REMOTE_HOST>:5173/
```

## 扫描流量开关

暂停扫描：

```bash
curl -X POST http://<REMOTE_HOST>:8000/api/scanner \
  -H 'Content-Type: application/json' \
  -d '{"enabled":false}'
```

恢复扫描：

```bash
curl -X POST http://<REMOTE_HOST>:8000/api/scanner \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true}'
```
