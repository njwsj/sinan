---
name: mock-metrics
description: 生成确定性的模拟指标数据（月度收入/成本/毛利）。触发词：mock、模拟数据、假数据、示例指标、demo 数据。当用户需要一份可用于页面演示的结构化指标数据、但没有真实数据源时使用。
output_type: data
keywords: mock,模拟数据,假数据,示例数据,demo数据,示例指标
requires_link: false
---

# mock-metrics

给页面生成流程提供一份**确定性**（同输入同输出，无随机数）的指标数据，
用于验证「Skill 输出 → GenerationState → Coder 写进图表」这条链路。

## 输入

handler.py 从 stdin 读一个 JSON：

```json
{"prompt": "用户原始需求", "session_id": "...", "marker": "...", "params": {"months": 6}}
```

## 输出

stdout 打印一个 JSON：

```json
{"ok": true, "content": {"columns": ["..."], "rows": ["..."], "summary": "..."}}
```

`rows` 每项形如 `{"month": "2026-01", "revenue": 1120, "cost": 728, "gross_profit": 392, "gross_margin": 0.35}`。
