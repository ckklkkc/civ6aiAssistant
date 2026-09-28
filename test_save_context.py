import struct
import tempfile
import zlib
from pathlib import Path

from save_context import MARKERS, parse_save

def tagged_int(marker: bytes, value: int) -> bytes:
    return marker + bytes([2]) + struct.pack('<i', value)

def tagged_string(marker: bytes, value: str) -> bytes:
    raw = value.encode('utf-8') + b'\x00'
    return marker + bytes([5]) + struct.pack('<I', len(raw)) + raw

def main():
    payload = b'TERRAIN_GRASS\x00RESOURCE_IRON\x00DISTRICT_CAMPUS\x00'
    fake = (
        b'CIV6' + b'\x00' * 16
        + tagged_int(MARKERS['game_turn'], 87)
        + tagged_string(MARKERS['game_speed'], 'GAMESPEED_STANDARD')
        + tagged_string(MARKERS['map_size'], 'MAPSIZE_STANDARD')
        + b'MOD_TITLE'
        + zlib.compress(payload)
    )

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'AUTO_SAVE_0087.Civ6Save'
        p.write_bytes(fake)
        ctx = parse_save(p)
        assert ctx['valid_magic'] is True
        assert ctx['header']['game_turn'] == 87
        assert ctx['header']['game_speed'] == 'GAMESPEED_STANDARD'
        assert ctx['header']['map_size'] == 'MAPSIZE_STANDARD'
        assert ctx['header']['map_width'] == 84
        assert ctx['header']['map_height'] == 54
        assert ctx['payload']['decompressed'] is True
        print('PASS')

if __name__ == '__main__':
    main()
