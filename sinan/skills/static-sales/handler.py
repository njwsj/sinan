# sinan/skills/static-sales/handler.py
"""static-sales Skill：读取包内静态数据集并返回。"""
import json
import sys
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "sales.json"


def main() -> int:
    sys.stdin.read()  # 协议要求读完 stdin，本 Skill 不使用输入
    if not _DATA.is_file():
        print(json.dumps({"ok": False, "error": f"data file missing: {_DATA}"}, ensure_ascii=False))
        return 0
    try:
        data = json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": f"read data failed: {e}"}, ensure_ascii=False))
        return 0

    rows = data.get("rows") or []
    data["row_count"] = len(rows)
    data["summary"] = f"静态销售数据集，{len(rows)} 行，维度：region × category。"
    print(json.dumps({"ok": True, "content": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())