---
name: static-sales
description: 读取内置的静态销售数据集（区域 × 品类销售额）。触发词：销售数据、区域销售、品类销售、销售看板、sales。当用户要做销售相关看板但未上传数据文件时使用。
output_type: data
keywords: 销售,销售额,区域销售,品类,sales
requires_link: false
---

# static-sales

把包内 `data/sales.json` 原样读出并归一化返回，用于验证
「静态数据 Skill → Artifact → Coder」链路。数据不随时间变化。