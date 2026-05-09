---
name: us-strategy-us-momo-swing-fast
description: 美股动量轮动（Fast 版，持仓6只）。自动构建候选池，T+1 执行，严格无未来函数。
---

# US Momo Swing Fast

## 能力

- 生成次日候选买入列表（默认 6 只）
- 回测验证 3m / 6m / 1y 收益与回撤
- 输出结构化 JSON，可直接给 `paper-trading` 下单层消费

## 策略参数（固定）

- `ma_fast=15`
- `ma_slow=120`
- `mom_lb=80`
- `top_k=6`
- `stop_loss=0.06`
- `exposure=1.30`
- `universe_keep=40`

## 时序与防作弊约束

- 仅使用 `t-1` 日线收盘后可见数据生成信号
- `t` 日执行（回测按 `t` 收益计入）
- 不读取买点后的任何未来数据用于当下决策
- 候选池来自自动榜单并集，不按主观板块挑票

## 运行

```bash
SKILL_DIR="/Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/us-strategy-us-momo-swing-fast"
python3 "$SKILL_DIR/scripts/backtest_validate.py" --asof 2026-05-10 --json
python3 "$SKILL_DIR/scripts/daily_decisions.py" --asof 2026-05-10 --json
```
