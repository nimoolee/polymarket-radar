# GitHub 发布与传播计划

## 推荐项目名

**EdgeRadar**

副标题：

> CLOB-first Polymarket intelligence dashboard for event-market research.

理由：

1. `Edge` 对交易研究用户有吸引力，但不承诺收益。
2. `Radar` 表达监控和发现，不暗示自动交易。
3. 名字短，适合 GitHub、域名、截图和社交平台传播。

## GitHub Topics

```text
polymarket
prediction-markets
event-markets
trading-dashboard
clob
websocket
fastapi
react
market-intelligence
```

## README 首屏要点

1. 一句话讲清楚：Gamma 发现市场，CLOB 校验真实盘口。
2. 明确不是自动交易机器人，降低合规和误用风险。
3. 放一张真实截图，展示高信息密度页面。
4. 放快速启动命令，减少试用门槛。
5. 放架构图，吸引工程用户收藏。

## 更容易获得收藏的功能方向

1. 录制 30 秒演示 GIF：暂停扫描、开始扫描、市场排序、CLOB/Gamma 偏差。
2. 增加 `sample-data` 模式：只用于离线演示，必须清晰标记为 sample，不能冒充真实数据。
3. 增加 Docker 一键启动，降低试用成本。
4. 增加外部数据源路线图：体育比分、天气实况、新闻/社媒、链上数据。
5. 增加公开 issue 标签：`good first issue`、`data-source`、`frontend`、`strategy-research`。

## 发布前检查清单

1. `.env` 不进入 Git。
2. README 能在新机器上跑通。
3. `npm run build` 通过。
4. `python3 -m compileall backend/app` 通过。
5. 页面默认不自动扫描，用户主动开启。
6. 截图不包含个人资产、账号、私有 IP 或敏感信息。

## 社交平台介绍文案

短版：

> I built EdgeRadar, a CLOB-first Polymarket intelligence dashboard. Gamma discovers markets, CLOB validates tradable prices, and the UI ranks opportunities by probability, spread, liquidity, freshness, and time risk.

中文版：

> EdgeRadar 是一个事件市场机会雷达：Gamma 负责发现市场，CLOB 负责校验真实可交易盘口，前端按概率、spread、流动性、盘口新鲜度和时间风险排序。它不是自动交易机器人，而是研究和监控工具。
