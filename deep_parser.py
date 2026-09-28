from __future__ import annotations

import struct
import zlib
from typing import Any

NONE = 0xFFFFFFFF
FLAG_OWNED = 0x40


def civ6_hash(name: str) -> int:
    return (~zlib.crc32(name.encode("utf-8"))) & 0xFFFFFFFF


TERRAIN_KEYS = [
    "TERRAIN_GRASS", "TERRAIN_GRASS_HILLS", "TERRAIN_GRASS_MOUNTAIN",
    "TERRAIN_PLAINS", "TERRAIN_PLAINS_HILLS", "TERRAIN_PLAINS_MOUNTAIN",
    "TERRAIN_DESERT", "TERRAIN_DESERT_HILLS", "TERRAIN_DESERT_MOUNTAIN",
    "TERRAIN_TUNDRA", "TERRAIN_TUNDRA_HILLS", "TERRAIN_TUNDRA_MOUNTAIN",
    "TERRAIN_SNOW", "TERRAIN_SNOW_HILLS", "TERRAIN_SNOW_MOUNTAIN",
    "TERRAIN_COAST", "TERRAIN_OCEAN",
]

FEATURE_KEYS = [
    "FEATURE_FOREST", "FEATURE_JUNGLE", "FEATURE_MARSH",
    "FEATURE_FLOODPLAINS", "FEATURE_FLOODPLAINS_GRASSLAND", "FEATURE_FLOODPLAINS_PLAINS",
    "FEATURE_OASIS", "FEATURE_ICE", "FEATURE_REEF", "FEATURE_GEOTHERMAL_FISSURE",
    "FEATURE_VOLCANIC_SOIL", "FEATURE_VOLCANO",
]

DISTRICT_KEYS = [
    "DISTRICT_CITY_CENTER", "DISTRICT_CAMPUS", "DISTRICT_HOLY_SITE",
    "DISTRICT_COMMERCIAL_HUB", "DISTRICT_HARBOR", "DISTRICT_ENCAMPMENT",
    "DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_THEATER", "DISTRICT_ENTERTAINMENT_COMPLEX",
    "DISTRICT_WATER_ENTERTAINMENT_COMPLEX", "DISTRICT_AQUEDUCT", "DISTRICT_NEIGHBORHOOD",
    "DISTRICT_SPACEPORT", "DISTRICT_GOVERNMENT", "DISTRICT_DIPLOMATIC_QUARTER",
    "DISTRICT_PRESERVE", "DISTRICT_DAM", "DISTRICT_CANAL", "DISTRICT_WONDER",
    "DISTRICT_AERODROME",
]

TERRAIN = {civ6_hash(k): k for k in TERRAIN_KEYS}
FEATURE = {civ6_hash(k): k for k in FEATURE_KEYS}
DISTRICT = {civ6_hash(k): k for k in DISTRICT_KEYS}


class ParseError(Exception):
    pass


def _u32(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 4 > len(data):
        raise ParseError("u32 out of range")
    return struct.unpack_from("<I", data, pos)[0]


def _u16(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 2 > len(data):
        raise ParseError("u16 out of range")
    return struct.unpack_from("<H", data, pos)[0]


def _i16(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 2 > len(data):
        raise ParseError("i16 out of range")
    return struct.unpack_from("<h", data, pos)[0]


def _u8(data: bytes, pos: int) -> int:
    if pos < 0 or pos >= len(data):
        raise ParseError("u8 out of range")
    return data[pos]


def _find_tile_candidates(body: bytes):
    n = len(body)
    for pos in range(0, n - 12):
        layer_count = _u32(body, pos)
        if not 1 <= layer_count <= 16:
            continue
        lo = _u32(body, pos + 4)
        hi = _u32(body, pos + 8)
        if hi != 15 or hi - lo + 1 != layer_count:
            continue

        id_pos = pos + 12
        ok = True
        for layer_id in range(lo, hi + 1):
            if id_pos + 4 > n or _u32(body, id_pos) != layer_id:
                ok = False
                break
            id_pos += 4
        if not ok or id_pos + 8 > n:
            continue
        if _u32(body, id_pos) != 6:
            continue
        tile_count = _u32(body, id_pos + 4)
        if 100 <= tile_count <= 100000:
            yield id_pos + 8, tile_count


def _read_tile(body: bytes, pos: int) -> tuple[dict[str, Any], int]:
    pos += 8
    pos += 4
    terrain = _u32(body, pos); pos += 4
    feature = _u32(body, pos); pos += 4
    pos += 2
    continent = _u32(body, pos); pos += 4
    units = _u8(body, pos); pos += 1
    resource = _u32(body, pos); pos += 4
    resource_count = _u16(body, pos); pos += 2
    improvement = _u32(body, pos); pos += 4
    pos += 1
    road_value = _i16(body, pos); pos += 2
    appeal = _i16(body, pos); pos += 2
    river_east = _u8(body, pos); pos += 1
    river_se = _u8(body, pos); pos += 1
    river_sw = _u8(body, pos); pos += 1
    pos += 1
    pos += 1
    cliff_map = _u8(body, pos); pos += 1
    pos += 1
    flags = _u8(body, pos); pos += 1
    pos += 1
    has_overlay = _u32(body, pos); pos += 4

    if has_overlay != 0:
        overlay_count = _u32(body, pos); pos += 4
        if overlay_count > 0xFFFF:
            raise ParseError("implausible overlay count")
        for _ in range(overlay_count):
            pos += 11
            value = _u32(body, pos); pos += 4
            pos += 1
            inner_count = _u32(body, pos); pos += 4
            if value != 0:
                pos += inner_count * 20
            if pos > len(body):
                raise ParseError("overlay overrun")

    owner = -1
    wonder = NONE
    city = -1
    district = -1
    if flags & FLAG_OWNED:
        city_value = _u32(body, pos); pos += 4
        pos += 4
        district_value = _u32(body, pos); pos += 4
        if city_value != NONE:
            city = city_value & 0xFFFF
        if district_value != NONE:
            district = district_value & 0xFFFF
        owner = _u8(body, pos); pos += 1
        if owner == 0xFF:
            owner = -1
        wonder = _u32(body, pos); pos += 4

    river_flags = (
        (1 if river_east != 0xFF else 0)
        | (2 if river_se != 0xFF else 0)
        | (4 if river_sw != 0xFF else 0)
    )

    return {
        "terrain_hash": terrain,
        "terrain": TERRAIN.get(terrain),
        "feature_hash": feature,
        "feature": None if feature == NONE else FEATURE.get(feature),
        "resource_hash": resource,
        "resource_count": resource_count,
        "improvement_hash": improvement,
        "continent_hash": continent,
        "appeal": appeal,
        "road": -1 if road_value == -1 else road_value & 0xFF,
        "river_flags": river_flags,
        "cliff_flags": cliff_map & 0b111,
        "wonder_hash": wonder,
        "owner": owner,
        "units": units,
        "city_id": city,
        "district_id": district,
    }, pos


def parse_map(body: bytes) -> dict[str, Any]:
    failures = 0
    for tiles_start, tile_count in _find_tile_candidates(body):
        try:
            pos = tiles_start
            tiles = []
            for idx in range(tile_count):
                tile, pos = _read_tile(body, pos)
                tile["index"] = idx
                tiles.append(tile)

            pos += 4
            width = _u32(body, pos)
            if width < 10 or width > 512 or tile_count % width != 0:
                raise ParseError("tile width checksum failed")
            height = tile_count // width

            for idx, tile in enumerate(tiles):
                tile["x"] = idx % width
                tile["y"] = idx // width

            return {
                "width": width,
                "height": height,
                "tile_count": tile_count,
                "tiles_start": tiles_start,
                "candidate_failures": failures,
                "tiles": tiles,
            }
        except (ParseError, struct.error, IndexError):
            failures += 1
            continue
    raise ParseError("Could not locate and parse tile array")


def parse_districts(body: bytes, parsed_map: dict[str, Any]) -> dict[int, dict[str, Any]]:
    width = parsed_map["width"]
    height = parsed_map["height"]
    tiles = parsed_map["tiles"]
    district_hashes = set(DISTRICT)
    votes: dict[tuple, tuple[int, int, int]] = {}

    for pos in range(16, len(body) - 4):
        h = _u32(body, pos)
        if h not in district_hashes:
            continue
        packed_id = _u32(body, pos - 16)
        x = _u32(body, pos - 12)
        y = _u32(body, pos - 8)
        packed_city = _u32(body, pos - 4)
        if packed_id == NONE or x >= width or y >= height:
            continue
        tile_index = y * width + x
        tile = tiles[tile_index]
        if tile["district_id"] != (packed_id & 0xFFFF):
            continue
        if tile["city_id"] >= 0 and packed_city != NONE and tile["city_id"] != (packed_city & 0xFFFF):
            continue
        key = (packed_id, x, y, packed_city, h)
        old = votes.get(key)
        votes[key] = (tile_index, h, (old[2] + 1) if old else 1)

    best: dict[int, tuple[int, int]] = {}
    for tile_index, h, count in votes.values():
        current = best.get(tile_index)
        if current is None or count > current[1]:
            best[tile_index] = (h, count)

    return {
        idx: {"hash": h, "type": DISTRICT.get(h), "votes": count}
        for idx, (h, count) in best.items()
    }


def _city_display_name(key: str) -> str:
    if not (key.startswith("LOC_CITY_NAME_") or key.startswith("CITY_NAME_")):
        return key
    trimmed = key.removeprefix("LOC_").removeprefix("CITY_NAME_")
    return " ".join(w[:1] + w[1:].lower() for w in trimmed.split("_") if w) or key


def _scan_city_name(body: bytes, start: int, end: int) -> str | None:
    marker = bytes([0x8E, 0x0F, 0x7F])
    pos = start
    while pos + 24 < end:
        idx = body.find(marker, pos, end)
        if idx < 0:
            return None
        length = _u32(body, idx + 20)
        if 0 < length <= 64 and idx + 24 + length <= len(body):
            raw = body[idx + 24:idx + 24 + length]
            if all(b >= 0x20 for b in raw):
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    pass
        pos = idx + 1
    return None


def parse_cities(body: bytes, parsed_map: dict[str, Any]) -> dict[int, dict[str, Any]]:
    width = parsed_map["width"]
    height = parsed_map["height"]
    tiles = parsed_map["tiles"]
    headers = []

    for pos in range(0, len(body) - 32):
        if body[pos] != 0x33 or _u32(body, pos) != 0x33:
            continue
        packed_id = _u32(body, pos + 4)
        x = _u32(body, pos + 8)
        y = _u32(body, pos + 12)
        owner = _u32(body, pos + 16)
        founder = _u32(body, pos + 20)
        previous_owner = _u32(body, pos + 24)
        if packed_id == NONE or x >= width or y >= height or owner >= 64:
            continue
        if founder >= 64 or previous_owner >= 64 or _u32(body, pos + 28) != NONE:
            continue
        tile_index = y * width + x
        tile = tiles[tile_index]
        if tile["owner"] != owner or tile["city_id"] != (packed_id & 0xFFFF):
            continue
        headers.append({
            "pos": pos, "tile_index": tile_index, "id": packed_id & 0xFFFF,
            "x": x, "y": y, "owner": owner,
        })

    cities: dict[int, dict[str, Any]] = {}
    for i, header in enumerate(headers):
        tile_index = header["tile_index"]
        if tile_index in cities:
            continue
        next_pos = headers[i + 1]["pos"] if i + 1 < len(headers) else len(body)
        end = min(next_pos, header["pos"] + 32 + 65536)
        key = _scan_city_name(body, header["pos"] + 32, end)
        cities[tile_index] = {
            "id": header["id"],
            "x": header["x"],
            "y": header["y"],
            "owner": header["owner"],
            "name": _city_display_name(key) if key else None,
        }
    return cities


def build_deep_state(body: bytes) -> dict[str, Any]:
    parsed_map = parse_map(body)
    districts = parse_districts(body, parsed_map)
    cities = parse_cities(body, parsed_map)

    for idx, district in districts.items():
        parsed_map["tiles"][idx]["district_type"] = district["type"]
        parsed_map["tiles"][idx]["district_hash"] = district["hash"]

    city_list = list(cities.values())
    district_list = []
    for idx, d in districts.items():
        tile = parsed_map["tiles"][idx]
        district_list.append({
            "x": tile["x"],
            "y": tile["y"],
            "owner": tile["owner"],
            "city_id": tile["city_id"],
            "district_id": tile["district_id"],
            "type": d["type"],
            "hash": d["hash"],
        })

    return {
        "map": parsed_map,
        "cities": city_list,
        "districts": district_list,
        "stats": {
            "cities": len(city_list),
            "districts": len(district_list),
            "known_terrain_tiles": sum(1 for t in parsed_map["tiles"] if t["terrain"]),
            "known_feature_tiles": sum(1 for t in parsed_map["tiles"] if t["feature"]),
        },
    }


def compact_deep_state(state: dict[str, Any], tile_limit: int = 120) -> dict[str, Any]:
    m = state["map"]
    important = []
    for tile in m["tiles"]:
        if (
            tile["owner"] >= 0
            or tile["city_id"] >= 0
            or tile["district_id"] >= 0
            or tile["resource_hash"] != NONE
            or tile["feature"] is not None
        ):
            important.append(tile)
        if len(important) >= tile_limit:
            break

    return {
        "map": {
            "width": m["width"],
            "height": m["height"],
            "tile_count": m["tile_count"],
            "tiles_start": m["tiles_start"],
            "candidate_failures": m["candidate_failures"],
        },
        "stats": state["stats"],
        "cities": state["cities"],
        "districts": state["districts"],
        "important_tiles_sample": important,
        "important_tiles_sample_truncated": len(important) >= tile_limit,
    }
