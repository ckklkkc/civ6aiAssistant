import json
import tempfile
from pathlib import Path

from mod_bridge import PREFIX, latest_snapshot, snapshot_for_prompt


def test_completed_session_and_partial_tail():
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "Lua.log"
        records = [{"kind": "meta", "turn": 10}, {"kind": "city", "name": "首都"},
                   {"kind": "plot", "x": 3, "y": 4}]
        lines = [f"[InGame] {PREFIX}100001|BEGIN|3|{{}}"]
        lines += [f"[InGame] {PREFIX}100001|ITEM|{i}|{json.dumps(item, ensure_ascii=False)}"
                  for i, item in enumerate(records, 1)]
        lines += [f"[InGame] {PREFIX}100001|END|3|{{}}",
                  f"[InGame] {PREFIX}100002|BEGIN|1|{{}}"]
        log.write_text("\n".join(lines), encoding="utf-8")
        state = latest_snapshot(str(log))
        assert state["status"] == "ok"
        assert state["meta"]["turn"] == 10
        assert state["cities"][0]["name"] == "首都"
        assert state["plots"][0]["x"] == 3
        assert "首都" in snapshot_for_prompt(state)
        log.write_text("\n".join(lines[:-2]), encoding="utf-8")
        assert latest_snapshot(str(log))["status"] == "snapshot_missing"


if __name__ == "__main__":
    test_completed_session_and_partial_tail()
    print("PASS")
