# Security Policy

## Supported Versions

当前项目处于早期版本，安全修复优先合并到主分支。

## Reporting a Vulnerability

请不要在公开 issue 中提交敏感信息、API token、服务器密码或私有地址。

如果发现安全问题，请在 GitHub 创建一个不包含敏感细节的 issue，说明影响范围；维护者会进一步沟通复现细节。

## Scope

当前项目默认不自动下单，也不保存交易所密钥。仍需注意：

- 不要提交 `backend/.env` 或 `frontend/.env`。
- 不要把没有鉴权的开发服务直接暴露到公网。
- 生产部署应使用 Nginx/HTTPS，并限制后端只监听内网或本机地址。
