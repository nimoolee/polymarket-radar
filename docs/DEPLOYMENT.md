# PolyMonitor 发布到 infinibyte.cn

## 推荐部署形态

生产环境建议使用一台 Linux VPS：

1. Nginx 对外提供 `https://infinibyte.cn`。
2. 前端 React/Vite 构建为静态文件，放在 `/opt/polymonitor/frontend/dist`。
3. 后端 FastAPI 只监听本机 `127.0.0.1:8000`。
4. Nginx 将 `/api/` 和 `/ws/` 反向代理到后端。
5. systemd 保持后端常驻运行，断网或重启后自动恢复。

不要把 Vite dev server 作为生产服务暴露到公网。

## 服务器准备

以 Ubuntu/Debian 为例：

```bash
sudo apt update
sudo apt install -y nginx python3 python3-venv python3-pip nodejs npm certbot python3-certbot-nginx
sudo useradd --system --create-home --shell /usr/sbin/nologin polymonitor || true
sudo mkdir -p /opt/polymonitor
sudo chown -R polymonitor:polymonitor /opt/polymonitor
```

## 上传代码

在本机项目目录执行：

```bash
rsync -av --delete \
  --exclude 'backend/.venv' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'logs' \
  /Users/infinity/Python/Poly_Codex/ \
  polymonitor@YOUR_SERVER_IP:/opt/polymonitor/
```

如果服务器禁止 `polymonitor` SSH 登录，可以先用你的普通用户上传，再执行：

```bash
sudo chown -R polymonitor:polymonitor /opt/polymonitor
```

## 后端安装

```bash
cd /opt/polymonitor/backend
sudo -u polymonitor python3 -m venv .venv
sudo -u polymonitor .venv/bin/pip install -r requirements.txt
sudo -u polymonitor cp .env.example .env
sudo -u polymonitor sed -i 's|POLL_INTERVAL_SECONDS=60|POLL_INTERVAL_SECONDS=180|' .env
```

确认 `/opt/polymonitor/backend/.env` 至少包含：

```bash
USE_MOCK_DATA=false
GAMMA_API_URL=https://gamma-api.polymarket.com
CLOB_WS_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
CORS_ORIGINS=https://infinibyte.cn,https://www.infinibyte.cn
```

## 前端构建

```bash
cd /opt/polymonitor/frontend
sudo -u polymonitor npm ci
sudo -u polymonitor npm run build -- --mode production
```

生产构建会使用同域名接口：

- REST：`/api/markets`
- WebSocket：`wss://infinibyte.cn/ws/market`

## systemd 后端服务

```bash
sudo cp /opt/polymonitor/deploy/systemd/polymonitor-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now polymonitor-backend
sudo systemctl status polymonitor-backend --no-pager
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

## Nginx

```bash
sudo cp /opt/polymonitor/deploy/nginx/infinibyte.cn.conf /etc/nginx/sites-available/infinibyte.cn
sudo ln -sf /etc/nginx/sites-available/infinibyte.cn /etc/nginx/sites-enabled/infinibyte.cn
sudo nginx -t
sudo systemctl reload nginx
```

确认 HTTP 可访问：

```bash
curl -I http://infinibyte.cn
curl http://infinibyte.cn/api/health
```

## HTTPS

域名 DNS A 记录指向服务器公网 IP 后执行：

```bash
sudo certbot --nginx -d infinibyte.cn -d www.infinibyte.cn
sudo systemctl reload nginx
```

验证：

```bash
curl -I https://infinibyte.cn
curl https://infinibyte.cn/api/health
```

## 更新发布

每次更新代码后：

```bash
cd /opt/polymonitor/backend
sudo -u polymonitor .venv/bin/pip install -r requirements.txt
sudo systemctl restart polymonitor-backend

cd /opt/polymonitor/frontend
sudo -u polymonitor npm ci
sudo -u polymonitor npm run build -- --mode production
sudo systemctl reload nginx
```

## 日志排查

```bash
sudo journalctl -u polymonitor-backend -f
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

## 注意

1. 当前系统没有登录鉴权，直接放到公网等于任何人都能看页面。正式公网发布前建议至少加 Basic Auth 或登录。
2. 后端默认只监听 `127.0.0.1:8000`，不要开放 8000 端口到公网。
3. WebSocket 必须走 Nginx `/ws/` 反代，否则前端实时数据不会连接。
