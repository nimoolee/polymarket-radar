# 生产部署说明

这是一份通用 Linux 部署说明，开源仓库中不包含项目维护者自己的域名、私有 IP、个人用户名或本机路径。

请按你的服务器情况设置以下变量。后续命令可以直接复制执行：

```bash
YOUR_DOMAIN=example.com
APP_DIR=/opt/polymarket-radar
APP_USER=polyradar
SSH_USER=your-ssh-user
YOUR_SERVER_IP=203.0.113.10
```

## 推荐部署形态

生产环境建议使用一台 Linux VPS：

1. Nginx 对外提供静态前端。
2. FastAPI 后端只监听本机 `127.0.0.1:8000`。
3. Nginx 将 `/api/` 和 `/ws/` 反向代理到后端。
4. systemd 保持后端常驻运行。
5. HTTPS 使用 Certbot 或你自己的证书方案。

不要把 Vite dev server 直接暴露到公网。

## 服务器准备

Ubuntu/Debian 示例：

```bash
sudo apt update
sudo apt install -y nginx python3 python3-venv python3-pip nodejs npm certbot python3-certbot-nginx

sudo useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER" || true
sudo mkdir -p "$APP_DIR"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
```

## 上传代码

在本地项目目录执行：

```bash
rsync -av --delete \
  --exclude '.git' \
  --exclude 'backend/.venv' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'logs' \
  ./ "$SSH_USER@$YOUR_SERVER_IP:$APP_DIR/"
```

然后在服务器上修正目录权限：

```bash
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
```

## 后端安装

```bash
cd "$APP_DIR/backend"
sudo -u "$APP_USER" python3 -m venv .venv
sudo -u "$APP_USER" .venv/bin/pip install -r requirements.txt
sudo -u "$APP_USER" cp .env.example .env
```

编辑 `$APP_DIR/backend/.env`：

```bash
USE_MOCK_DATA=false
GAMMA_API_URL=https://gamma-api.polymarket.com
CLOB_WS_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
CLOB_API_URL=https://clob.polymarket.com
POLL_INTERVAL_SECONDS=180
SCANNING_ENABLED_DEFAULT=false
CORS_ORIGINS=https://example.com
```

## 前端构建

```bash
cd "$APP_DIR/frontend"
sudo -u "$APP_USER" npm ci
sudo -u "$APP_USER" npm run build -- --mode production
```

生产构建默认使用同域名接口：

- REST：`/api/markets`
- WebSocket：`/ws/market`

## systemd 后端服务

复制 systemd 模板并替换路径和用户：

```bash
sudo cp "$APP_DIR/deploy/systemd/polymonitor-backend.service" /etc/systemd/system/polymarket-radar-backend.service
sudo sed -i "s|/opt/polymarket-radar|$APP_DIR|g" /etc/systemd/system/polymarket-radar-backend.service
sudo sed -i "s|User=polyradar|User=$APP_USER|g" /etc/systemd/system/polymarket-radar-backend.service
sudo sed -i "s|Group=polyradar|Group=$APP_USER|g" /etc/systemd/system/polymarket-radar-backend.service

sudo systemctl daemon-reload
sudo systemctl enable --now polymarket-radar-backend
sudo systemctl status polymarket-radar-backend --no-pager
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

## Nginx

复制通用 Nginx 模板并替换域名和目录：

```bash
sudo cp "$APP_DIR/deploy/nginx/polymarket-radar.conf" /etc/nginx/sites-available/polymarket-radar
sudo sed -i "s|<YOUR_DOMAIN>|$YOUR_DOMAIN|g" /etc/nginx/sites-available/polymarket-radar
sudo sed -i "s|<APP_DIR>|$APP_DIR|g" /etc/nginx/sites-available/polymarket-radar
sudo ln -sf /etc/nginx/sites-available/polymarket-radar /etc/nginx/sites-enabled/polymarket-radar
sudo nginx -t
sudo systemctl reload nginx
```

验证 HTTP：

```bash
curl -I "http://$YOUR_DOMAIN"
curl "http://$YOUR_DOMAIN/api/health"
```

## HTTPS

确认域名 DNS A 记录已指向服务器后执行：

```bash
sudo certbot --nginx -d "$YOUR_DOMAIN"
sudo systemctl reload nginx
```

验证：

```bash
curl -I "https://$YOUR_DOMAIN"
curl "https://$YOUR_DOMAIN/api/health"
```

## 更新发布

```bash
cd "$APP_DIR/backend"
sudo -u "$APP_USER" .venv/bin/pip install -r requirements.txt
sudo systemctl restart polymarket-radar-backend

cd "$APP_DIR/frontend"
sudo -u "$APP_USER" npm ci
sudo -u "$APP_USER" npm run build -- --mode production
sudo systemctl reload nginx
```

## 日志排查

```bash
sudo journalctl -u polymarket-radar-backend -f
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

## 安全注意事项

1. 本项目默认不包含登录鉴权。
2. 如果部署到公网，建议至少增加 Basic Auth、SSO、VPN 或其他访问控制。
3. 不要把后端 `8000` 端口直接暴露到公网。
4. `.env` 文件必须保持私有，不要提交真实密钥、私有域名或内部主机信息。
