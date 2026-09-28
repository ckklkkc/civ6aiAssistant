"""Parse complete Civ VI UI-mod snapshots from Lua.log, without reading hidden map data."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MARKER = "CIV6AI_V2|"
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 4000


def log_candidates() -> list[Path]:
    explicit = os.environ.get("CIV6_LUA_LOG")
    if explicit:
        return [Path(os.path.expandvars(os.path.expanduser(explicit)))]
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    roots = [home / "Documents"]
    for name in ("OneDrive", "OneDriveConsumer"):
        if os.environ.get(name):
            roots.append(Path(os.environ[name]) / "Documents")
    return [local / "Firaxis Games" / "Sid Meier's Civilization VI" / "Logs" / "Lua.log"] + [
        root / "My Games" / "Sid Meier's Civilization VI" / "Logs" / "Lua.log" for root in roots
    ]


def read_snapshot(paths: list[Path] | None = None) -> dict:
    found = [path for path in (paths if paths is not None else log_candidates()) if path.is_file()]
    if not found:
        return {"status": "no_log", "message": "找不到 Lua.log；請先在遊戲按「匯出局勢」。"}
    path = max(found, key=lambda p: p.stat().st_mtime)
    try:
        with path.open("rb") as handle:
            start = max(0, path.stat().st_size - MAX_LOG_BYTES)
            handle.seek(start)
            if start:
                handle.readline()
            lines = handle.read().decode("utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        return {"status": "read_error", "message": str(exc)}

    active = None
    latest = None
    for line in lines:
        position = line.find(MARKER)
        if position < 0:
            continue
        parts = line[position + len(MARKER):].split("|", 3)
        if len(parts) != 4:
            continue
        token, action, serial, body = parts
        if not token.isdigit() or not serial.isdigit():
            continue
        number = int(serial)
        if action == "BEGIN":
            active = {"token": token, "expected": number, "items": [], "invalid": number > MAX_ITEMS}
        elif active and token == active["token"] and action == "ITEM":
            if number != len(active["items"]) + 1 or active["invalid"]:
                active["invalid"] = True
                continue
            try:
                item = json.loads(body)
                if not isinstance(item, dict) or "kind" not in item:
                    raise ValueError("invalid item")
                active["items"].append(item)
            except (ValueError, json.JSONDecodeError):
                active["invalid"] = True
        elif active and token == active["token"] and action == "END":
            if not active["invalid"] and number == active["expected"] == len(active["items"]):
                items = active["items"]
                if items and items[0].get("kind") == "meta":
                    latest = items
            active = None
    if latest is None:
        return {"status": "no_snapshot", "message": "日誌內沒有完整的局勢資料；請在遊戲按「匯出局勢」。"}
    return {
        "status": "ok", "source": "civ6_ui_mod", "visibility": "currently_visible",
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "meta": latest[0],
        "cities": [item for item in latest[1:] if item["kind"] == "city"],
        "units": [item for item in latest[1:] if item["kind"] == "unit"],
        "plots": [item for item in latest[1:] if item["kind"] == "plot"],
    }
