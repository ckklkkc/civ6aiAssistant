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

MOD_TITLE_MARKER = bytes.fromhex("72E13430")
END_UNCOMPRESSED = bytes([0x00, 0x00, 0x01, 0x00])
COMPRESSED_DATA_END = bytes([0x00, 0x00, 0xFF, 0xFF])

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


def _iter_marker_positions(data: bytes, marker: bytes):
    start = 0
    while True:
        pos = data.find(marker, start)
        if pos < 0:
            return
        yield pos
        start = pos + 1


def _entry_type(data: bytes, pos: int) -> int | None:
    if pos + 8 > len(data):
        return None
    return struct.unpack_from("<I", data, pos + 4)[0]


def _read_int_entry(data: bytes, pos: int) -> int | None:
    if _entry_type(data, pos) != 2:
        return None
    value_pos = pos + 16
    if value_pos + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, value_pos)[0]


def _read_string_entry(data: bytes, pos: int) -> str | None:
    entry_type = _entry_type(data, pos)
    if entry_type not in (4, 5, 6):
        return None

    value_pos = pos + 8
    if value_pos + 8 > len(data):
        return None

    if entry_type in (4, 5):
        str_len = struct.unpack_from("<H", data, value_pos)[0]
        sig = data[value_pos + 2:value_pos + 8]
        if len(sig) != 6 or sig[1] != 0x21:
            return None
        start = value_pos + 8
        if str_len <= 0 or str_len > 4096 or start >= len(data):
            return None
        end = min(len(data), start + str_len)
        raw = data[start:end]
        null = raw.find(b"\x00")
        if null >= 0:
            raw = raw[:null]
        try:
            value = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            value = raw.decode("latin-1", errors="ignore").strip()
        return value or None

    char_count = struct.unpack_from("<H", data, value_pos)[0]
    sig = data[value_pos + 2:value_pos + 8]
    if len(sig) != 6 or sig[1] != 0x21:
        return None
    start = value_pos + 8
    byte_len = char_count * 2
    if char_count <= 0 or char_count > 4096 or start + byte_len > len(data):
        return None
    raw = data[start:start + byte_len]
    if raw.endswith(b"\x00\x00"):
        raw = raw[:-2]
    try:
        value = raw.decode("utf-16-le").strip()
    except UnicodeDecodeError:
        return None
    return value or None


def _pick_game_turn(data: bytes) -> tuple[int | None, str]:
    candidates = []
    for pos in _iter_marker_positions(data, MARKERS["game_turn"]):
        value = _read_int_entry(data, pos)
        if value is not None and 0 <= value <= 5000:
            candidates.append(value)
    if not candidates:
        return None, "unavailable"
    nonzero = [v for v in candidates if v > 0]
    chosen = nonzero[0] if nonzero else candidates[0]
    confidence = "high" if len(set(candidates)) == 1 else "medium"
    return chosen, confidence


def _pick_prefixed_string(data: bytes, marker: bytes, prefix: str) -> tuple[str | None, str]:
    candidates = []
    for pos in _iter_marker_positions(data, marker):
        value = _read_string_entry(data, pos)
        if isinstance(value, str) and value.startswith(prefix):
            candidates.append(value)
    if not candidates:
        return None, "unavailable"
    chosen = candidates[0]
    confidence = "high" if len(set(candidates)) == 1 else "medium"
    return chosen, confidence


def _strip_chunk_spacers(comp_data: bytes) -> bytes:
    chunk_size = 64 * 1024
    chunks = []
    pos = 0
    while pos < len(comp_data):
        chunks.append(comp_data[pos:pos + chunk_size])
        pos += chunk_size + 4
    return b"".join(chunks)


def _find_compressed_payload(data: bytes) -> tuple[int | None, bytes | None, str | None]:
    search_start = max(0, data.rfind(MOD_TITLE_MARKER))
    cursor = search_start

    while True:
        end_header = data.find(END_UNCOMPRESSED, cursor)
        if end_header < 0:
            break
        stream_start = end_header + 4
        if data[stream_start:stream_start + 2] in (b"\x78\x9c", b"\x78\xda", b"\x78\x01"):
            stream_end = data.rfind(COMPRESSED_DATA_END)
            if stream_end > stream_start:
                comp_data = data[stream_start:stream_end + 4]
                combined = _strip_chunk_spacers(comp_data)
                try:
                    d = zlib.decompressobj()
                    payload = d.decompress(combined)
                    payload += d.flush(zlib.Z_SYNC_FLUSH)
                    if payload:
                        return stream_start, payload, None
                except zlib.error:
                    pass
        cursor = end_header + 1

    for magic in (b"\x78\x9c", b"\x78\xda", b"\x78\x01"):
        start = data.find(magic, search_start)
        while start >= 0:
            stream_end = data.rfind(COMPRESSED_DATA_END)
            if stream_end > start:
                combined = _strip_chunk_spacers(data[start:stream_end + 4])
                try:
                    d = zlib.decompressobj()
                    payload = d.decompress(combined)
                    payload += d.flush(zlib.Z_SYNC_FLUSH)
                    if payload:
                        return start, payload, None
                except zlib.error:
                    pass
            start = data.find(magic, start + 1)

    return None, None, "找不到可依 Civ6 64KiB chunk/spacer 規則解壓的 game-data payload"


def _extract_printable_evidence(payload: bytes, prefixes: Iterable[bytes], limit: int = 40) -> list[str]:
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


def _marker_diagnostics(data: bytes) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for name, marker in MARKERS.items():
        rows = []
        for pos in list(_iter_marker_positions(data, marker))[:10]:
            rows.append({
                "offset": pos,
                "type_uint32": _entry_type(data, pos),
                "bytes_hex": data[pos:pos + 48].hex(" "),
            })
        out[name] = rows
    return out


def parse_save(path: Path, include_payload_metadata: bool = True, include_diagnostics: bool = False) -> dict[str, Any]:
    raw = path.read_bytes()

    game_turn, turn_conf = _pick_game_turn(raw)
    game_speed, speed_conf = _pick_prefixed_string(raw, MARKERS["game_speed"], "GAMESPEED_")
    map_size, map_conf = _pick_prefixed_string(raw, MARKERS["map_size"], "MAPSIZE_")

    result: dict[str, Any] = {
        "source": "civ6_save",
        "file": str(path),
        "file_name": path.name,
        "size_bytes": len(raw),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "valid_magic": raw.startswith(b"CIV6"),
        "header": {
            "game_turn": game_turn,
            "game_speed": game_speed,
            "map_size": map_size,
        },
        "payload": {},
        "confidence": {
            "game_turn": turn_conf,
            "game_speed": speed_conf,
            "map_size": map_conf,
        },
    }

    if map_size in MAP_DIMENSIONS:
        w, h = MAP_DIMENSIONS[map_size]
        result["header"]["map_width"] = w
        result["header"]["map_height"] = h
        result["header"]["tile_count"] = w * h

    if include_payload_metadata:
        offset, payload, error = _find_compressed_payload(raw)
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

    if include_diagnostics:
        result["diagnostics"] = {
            "marker_entries": _marker_diagnostics(raw),
            "end_uncompressed_count": raw.count(END_UNCOMPRESSED),
            "compressed_data_end_count": raw.count(COMPRESSED_DATA_END),
            "mod_title_marker_count": raw.count(MOD_TITLE_MARKER),
        }

    result["capabilities"] = {
        "authoritative_now": ["save_file_identity", "save_modified_time"],
        "header_fields_when_detected": ["game_turn", "game_speed", "map_size"],
        "payload_decompression": bool(result["payload"].get("decompressed")),
        "deep_map_city_unit_parser": False,
    }
    result["limitations"] = [
        "目前只把通過型別與內容驗證的 header 欄位標為可用；不再把可疑 marker 命中當成高可信度。",
        "已依 Civ6 社群 parser 的 64KiB chunk + 4-byte spacer 規則解壓 game-data，但尚未完成 tile/city/unit deep parser。",
        "若遊戲版本/DLC 導致格式差異，欄位會回傳 null/unavailable，而不是猜值。",
    ]
    return result


def build_context(config: Civ6ContextConfig, include_diagnostics: bool = False) -> dict[str, Any]:
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
        parsed = parse_save(
            save,
            include_payload_metadata=config.include_payload_metadata,
            include_diagnostics=include_diagnostics,
        )
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
        "~~~json\n" + body + "\n~~~"
    )
