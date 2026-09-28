"""Read completed, player-visible snapshots emitted by the Civ VI UI mod."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "CIV6_ASSISTANT_V1|"
MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 3000


def candidate_logs(explicit: str = "") -> list[Path]:
    if explicit:
        return [Path(os.path.expandvars(os.path.expanduser(explicit)))]
    base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    localappdata = Path(os.environ.get("LOCALAPPDATA", str(base / "AppData" / "Local")))
    roots = [base / "Documents"]
    for key in ("OneDrive", "OneDriveConsumer"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]) / "Documents")
    return ([localappdata / "Firaxis Games" / "Sid Meier's Civilization VI" / "Logs" / "Lua.log"]
            + [root / "My Games" / "Sid Meier's Civilization VI" / "Logs" / "Lua.log" for root in roots])


def latest_snapshot(explicit: str = "") -> dict:
    paths = [p for p in candidate_logs(explicit) if p.is_file()]
    if not paths:
        return {"status": "log_missing", "message": "找不到 Lua.log；請啟用 LoggingEnabled 並在遊戲中按『匯出局勢』。"}
    path = max(paths, key=lambda p: p.stat().st_mtime)
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - MAX_LOG_BYTES))
            if handle.tell():
                handle.readline()  # discard a partial first line
            data = handle.read().decode("utf-8-sig", errors="replace")
        sessions: dict[str, dict] = {}
        for line in data.splitlines():
            position = line.find(PREFIX)
            if position < 0:
                continue
            fields = line[position + len(PREFIX):].strip().split("|", 3)
            if len(fields) != 4:
                continue
            session, part, sequence, payload = fields
            if not session.isdigit() or not sequence.isdigit():
                continue
            if part == "BEGIN":
                sessions[session] = {"items": [], "expected": int(sequence), "complete": False}
            elif session in sessions and part == "ITEM":
                record = sessions[session]
                if len(record["items"]) < MAX_RECORDS and int(sequence) == len(record["items"]) + 1:
                    try:
                        record["items"].append(json.loads(payload))
                    except json.JSONDecodeError:
                        record["invalid"] = True
            elif session in sessions and part == "END":
                record = sessions[session]
                record["complete"] = (int(sequence) == len(record["items"]) == record["expected"]
                                     and not record.get("invalid"))
        complete = [s for s in sessions.values() if s["complete"]]
        if not complete:
            return {"status": "snapshot_missing", "message": "日誌中尚無完整快照；請在遊戲中按『匯出局勢』。"}
        items = complete[-1]["items"]
        if not items or items[0].get("kind") != "meta":
            return {"status": "snapshot_invalid"}
        return {
            "status": "ok", "source": "ui_mod", "scope": "local_player_currently_visible_only",
            "log_modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "meta": items[0],
            "cities": [i for i in items[1:] if i.get("kind") == "city"],
            "plots": [i for i in items[1:] if i.get("kind") == "plot"],
            "units": [i for i in items[1:] if i.get("kind") == "unit"],
        }
    except OSError as exc:
        return {"status": "log_error", "message": str(exc)}


def snapshot_for_prompt(snapshot: dict, limit: int = 16000) -> str:
    """Keep city and unit info, then trim plot records as a whole."""
    if snapshot.get("status") != "ok":
        return ""
    core = {key: snapshot[key] for key in ("source", "scope", "log_modified_utc", "meta", "cities", "units")}
    core["plots"] = []
    def encoded():
        return json.dumps(core, ensure_ascii=False, separators=(",", ":"))
    while len(encoded()) > limit and core["units"]:
        core["units"].pop()
    while len(encoded()) > limit and core["cities"]:
        core["cities"].pop()
    for plot in snapshot["plots"]:
        core["plots"].append(plot)
        if len(encoded()) > limit:
            core["plots"].pop()
            break
    core["plots_truncated"] = len(core["plots"]) < len(snapshot["plots"])
    return "遊戲內模組提供的玩家已探索資訊（僅供建議，不代表建造合法性）：\n" + encoded()
