"""Read-only checks for the observed decrypted R15 1.06.10 inner records.

No decryption, image generation, router access or flash writing. Passing does
not validate the outer container, trailer, signature, installed board or layout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

MAX_BYTES = 64 * 1024 * 1024
ROM_ID = b'DLK6E7001001'
RECORDS = ((9, 'mydlink'), (4, 'kernel'), (8, 'rootfs'))


def checksum(data, initial=0):
    """Vendor 16-bit end-around sum; odd trailing byte is padded with 0xff."""
    view = memoryview(data)
    even = len(view) & ~1
    total = initial + sum(v[0] for v in struct.iter_unpack('>H', view[:even]))
    if even != len(view):
        total += (view[-1] << 8) | 0xff
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return total


def inspect(data):
    if len(data) > MAX_BYTES or len(data) < 16 or data[:4] != b'MH01':
        raise ValueError('Expected the observed decrypted MH01 inner container within 64 MiB')
    offset = 16
    records = []
    for expected_kind, label in RECORDS:
        if offset + 80 > len(data):
            raise ValueError('Truncated record header: ' + label)
        header = data[offset:offset+80]
        if header[:12] != ROM_ID:
            raise ValueError('Unexpected record ROM ID: ' + label)
        if checksum(header) != 0xffff:
            raise ValueError('Record header checksum mismatch: ' + label)
        if header[70] != expected_kind:
            raise ValueError('Unexpected record kind/order: ' + label)
        length = int.from_bytes(header[44:48], 'big')
        start, end = offset + 80, offset + 80 + length
        if not length or end > len(data):
            raise ValueError('Empty or truncated record payload: ' + label)
        payload = memoryview(data)[start:end]
        stored = int.from_bytes(header[14:16], 'big')
        if checksum(payload) != stored:
            raise ValueError('Record payload checksum mismatch: ' + label)
        records.append({'kind': label, 'record_offset': offset, 'payload_offset': start,
                        'payload_bytes': length, 'header_checksum': 'pass',
                        'payload_checksum': 'pass', 'payload_sha256': hashlib.sha256(payload).hexdigest()})
        offset = end
    # This inspector deliberately supports the single observed stock layout.
    if len(data)-offset != 256:
        raise ValueError('Unexpected trailing length; observed stock layout has 256 bytes')
    return {'scope': 'Observed R15 1.06.10 decrypted inner-record integrity only',
            'input_sha256': hashlib.sha256(data).hexdigest(), 'records': records,
            'trailing_bytes': 256, 'trailer_validated': False, 'outer_container_validated': False,
            'authenticity_verified': False, 'board_compatibility_verified': False,
            'flash_layout_verified': False, 'flashable': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decrypted_input', type=Path)
    args = parser.parse_args()
    try:
        with args.decrypted_input.open('rb') as stream:
            result = inspect(stream.read(MAX_BYTES + 1))
    except (ValueError, OSError) as error:
        print(json.dumps({'error': str(error), 'flashable': False}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
