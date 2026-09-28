from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MARKERS = {
    "game_turn": bytes.fromhex("9D2CE6BD"),
    "game_speed": bytes.fromhex("99B0D905"),
    "map_size": bytes.fromhex("405C830B"),
}

MAP_DIMENSIONS = {
    "MAPSIZE_DUEL": (44, 26),
    "MAPSIZE_TINY": (60, 38),
    "MAPSIZE_SMALL": (74, 46),
    "MAPSIZE_STANDARD": (84, 54),
    "MAPSIZE_LARGE": (96, 60),
    "MAPSIZE_HUGE": (106, 66),
}

@dataclass
class Civ6ContextConfig:
    enabled: bool = True
    save_dir: str = ""
    max_context_chars: int = 12000
    include_payload_metadata: bool = True

def _candidate_save_dirs(explicit: str = "") -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(explicit))))

    home = Path.home()
    userprofile = Path(os.environ.get("USERPROFILE", str(home)))
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")

    bases = [home / "Documents", userprofile / "Documents"]
    if onedrive:
        bases.append(Path(onedrive) / "Documents")

    for base in bases:
        root = base / "My Games" / "Sid Meier's Civilization VI" / "Saves"
        candidates.extend([root / "Single" / "Auto", root / "Single", root])

    seen = set()
    unique = []
    for p in candidates:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique

def find_latest_save(explicit_dir: str = "") -> Path | None:
    saves: list[Path] = []
    for root in _candidate_save_dirs(explicit_dir):
        if not root.exists() or not root.is_dir():
            continue
        try:
            saves.extend(root.rglob("*.Civ6Save"))
        except OSError:
            continue
    if not saves:
        return None
    return max(saves, key=lambda p: p.stat().st_mtime)

def _read_typed_value(data: bytes, marker: bytes) -> Any:
    pos = data.find(marker)
    if pos < 0:
        return None
    cursor = pos + len(marker)
    if cursor >= len(data):
        return None

    type_code = data[cursor]
    cursor += 1

    if type_code == 2 and cursor + 4 <= len(data):
        return struct.unpack_from("<i", data, cursor)[0]

    if type_code in (5, 6):
        if cursor + 4 <= len(data):
            length = struct.unpack_from("<I", data, cursor)[0]
            if 0 < length < 4096 and cursor + 4 + length <= len(data):
                raw = data[cursor + 4: cursor + 4 + length].rstrip(b"\x00")
                for enc in ("utf-8", "utf-16-le", "latin-1"):
                    try:
                        value = raw.decode(enc).strip("\x00\r\n\t ")
                        if value:
                            return value
                    except UnicodeDecodeError:
                        pass

        window = data[cursor: cursor + 256]
        token = bytearray()
        for b in window:
            if 32 <= b <= 126:
                token.append(b)
            elif token:
                break
        if token:
            return token.decode("ascii", errors="ignore")
    return None

def _find_zlib_payload(data: bytes) -> tuple[int | None, bytes | None, str | None]:
    start_at = max(0, data.rfind(b"MOD_TITLE"))
    headers = (b"\x78\x9c", b"\x78\xda", b"\x78\x01")
    positions = []
    for magic in headers:
        idx = data.find(magic, start_at)
        if idx >= 0:
            positions.append(idx)

    for idx in sorted(set(positions)):
        try:
            payload = zlib.decompress(data[idx:])
            return idx, payload, None
        except zlib.error:
            continue
    return None, None, "找不到可完整解壓的 zlib game-data payload"

def _extract_printable_evidence(payload: bytes, prefixes: Iterable[bytes], limit: int = 30) -> list[str]:
    found: list[str] = []
    seen = set()
    for prefix in prefixes:
        start = 0
        while len(found) < limit:
            idx = payload.find(prefix, start)
            if idx < 0:
                break
            end = idx
            while end < len(payload) and end - idx < 96:
                b = payload[end]
                if not (32 <= b <= 126):
                    break
                end += 1
            token = payload[idx:end].decode("ascii", errors="ignore")
            if token and token not in seen:
                seen.add(token)
                found.append(token)
            start = idx + len(prefix)
    return found

def parse_save(path: Path, include_payload_metadata: bool = True) -> dict[str, Any]:
    raw = path.read_bytes()
    result: dict[str, Any] = {
        "source": "civ6_save",
        "file": str(path),
        "file_name": path.name,
        "size_bytes": len(raw),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "valid_magic": raw.startswith(b"CIV6"),
        "header": {},
        "payload": {},
        "confidence": {},
    }

    for key, marker in MARKERS.items():
        value = _read_typed_value(raw, marker)
        result["header"][key] = value
        result["confidence"][key] = "high" if value is not None else "unavailable"

    map_size = result["header"].get("map_size")
    if isinstance(map_size, str) and map_size in MAP_DIMENSIONS:
        w, h = MAP_DIMENSIONS[map_size]
        result["header"]["map_width"] = w
        result["header"]["map_height"] = h
        result["header"]["tile_count"] = w * h

    if include_payload_metadata:
        offset, payload, error = _find_zlib_payload(raw)
        result["payload"]["offset"] = offset
        result["payload"]["decompressed"] = payload is not None
        if payload is not None:
            result["payload"]["decompressed_bytes"] = len(payload)
            result["payload"]["identifier_evidence"] = _extract_printable_evidence(
                payload,
                prefixes=(b"TERRAIN_", b"FEATURE_", b"RESOURCE_", b"DISTRICT_", b"UNIT_", b"BUILDING_"),
                limit=40,
            )
        else:
            result["payload"]["error"] = error

    result["capabilities"] = {
        "authoritative_now": ["save_file_identity", "save_modified_time"],
        "header_fields_when_detected": ["game_turn", "game_speed", "map_size"],
        "payload_decompression": bool(result["payload"].get("decompressed")),
        "deep_map_city_unit_parser": False,
    }
    result["limitations"] = [
        "此第一版不會把 binary payload 中的 tile/city/unit 結構硬猜成精確資料。",
        "若 header 標記因遊戲版本/DLC 改變而無法辨識，欄位會回傳 null 並自動降級。",
        "地圖格、城市、單位的精確解析應由後續 deep parser 或 Civ6 Lua exporter 提供。",
    ]
    return result

def build_context(config: Civ6ContextConfig) -> dict[str, Any]:
    if not config.enabled:
        return {"enabled": False, "status": "disabled"}

    save = find_latest_save(config.save_dir)
    if not save:
        return {
            "enabled": True,
            "status": "save_not_found",
            "searched": [str(p) for p in _candidate_save_dirs(config.save_dir)],
        }

    try:
        parsed = parse_save(save, include_payload_metadata=config.include_payload_metadata)
        parsed["enabled"] = True
        parsed["status"] = "ok"
        return parsed
    except Exception as exc:
        return {
            "enabled": True,
            "status": "parse_error",
            "file": str(save),
            "error": f"{type(exc).__name__}: {exc}",
        }

def context_for_prompt(context: dict[str, Any], max_chars: int = 12000) -> str:
    body = json.dumps(context, ensure_ascii=False, indent=2)
    if len(body) > max_chars:
        body = body[:max_chars] + "\n...<truncated>"

    return (
        "以下是由本機 Civilization VI 存檔取得的結構化輔助資料。\n"
        "規則：只把明確解析出的欄位當作事實；null、limitations、identifier_evidence 都不可自行補完或當成精確遊戲狀態。\n"
        "若結構化資料與截圖衝突，請指出衝突並優先採用明確、可信度較高的資料；若資料不足，才使用截圖做視覺推論。\n"
        "```json\n" + body + "\n```"
    )
