
# sinan/skills/mock-metrics/handler.py
"""mock-metrics Skill 的执行入口。

约定（sinan Skill 协议）：
  - 从 stdin 读一个 JSON：{prompt, session_id, marker, params}
  - 向 stdout 打印一个 JSON：{ok, content, error?}
  - 退出码 0 表示进程正常；业务失败用 ok=false 表达，不要靠退出码
  - 不读环境变量里的凭证，不出网（学习项目约束）
"""
import json
import sys

_BASE_REVENUE = 1000


def build_rows(months: int) -> list[dict]:
    """确定性造数：第 i 个月收入 = 1000 + 120*i，成本 = 收入 * 0.65。"""
    rows = []
    for i in range(months):
        month = f"2026-{i + 1:02d}"
        revenue = _BASE_REVENUE + 120 * i
        cost = round(revenue * 0.65, 2)
        rows.append({
            "month": month,
            "revenue": revenue,
            "cost": cost,
            "gross_profit": round(revenue - cost, 2),
            "gross_margin": round((revenue - cost) / revenue, 4),
        })
    return rows


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"invalid stdin json: {e}"}, ensure_ascii=False))
        return 0

    params = payload.get("params") or {}
    try:
        months = int(params.get("months") or 6)
    except (TypeError, ValueError):
        months = 6
    months = max(1, min(months, 24))

    rows = build_rows(months)
    print(json.dumps({
        "ok": True,
        "content": {
            "columns": ["month", "revenue", "cost", "gross_profit", "gross_margin"],
            "rows": rows,
            "row_count": len(rows),
            "summary": f"共 {len(rows)} 个月的模拟指标数据，收入线性增长，成本率恒定 65%。",
        },
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())