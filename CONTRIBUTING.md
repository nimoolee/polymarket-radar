# Contributing

感谢你关注 EdgeRadar。这个项目的优先级是数据准确、系统稳定和可解释，不追求未经验证的交易信号。

## 开发原则

1. 不用 mock 数据冒充真实数据。
2. Gamma 只用于市场发现，交易判断必须优先看 CLOB。
3. 不新增自动下单功能，除非有明确的安全设计和用户确认。
4. 新增市场类型时，必须说明时间解释逻辑。
5. 新增策略或评分逻辑时，必须说明 spread、流动性、延迟和关闭风险。

## 本地开发

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## 提交前检查

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app
cd frontend && npm run build
```

## Pull Request 建议

- 说明修改目的。
- 说明影响的市场类型。
- 说明是否影响扫描频率、CLOB token 数量或前端排序。
- 如果涉及时间解释，请给出至少一个真实市场例子。
