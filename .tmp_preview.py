import json
from pathlib import Path
res = json.loads(Path("logs/qa_sessions/qa_run_20260101_answers_nocache.json").read_text(encoding="utf-8"))
for item in res:
    ans = item.get("answer") or ""
    short = ans.replace("\n", " ")[:180]
    missing = ("未提及" in ans) or ("未提到" in ans)
    print(f"[{item['index']:02d}] {item['question']}\n  status={item['status']} miss_note={'缺信息' if missing else ''}\n  preview: {short}\n")