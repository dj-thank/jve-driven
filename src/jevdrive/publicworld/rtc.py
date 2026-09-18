"""Extract legacy CESIUM_RTC without changing geometry, images, or buffer offsets.

Cesium's model transform composes tile * b3dm RTC * glTF RTC * axis correction.
Centers are application/tile coordinates, NOT glTF Y-up vertex coordinates.
References: CesiumGS/cesium GltfLoader, Model/B3dmLoader, Model/ModelSceneGraph;
https://www.mlit.go.jp/plateau/learning/tpc12-2/
"""
from __future__ import annotations
import hashlib
import json
import math
import struct


def extract_cesium_rtc(data: bytes):
    if len(data) < 20 or struct.unpack_from('<4sII', data) != (b'glTF', 2, len(data)):
        raise ValueError('Expected a complete glTF 2 GLB')
    length, kind = struct.unpack_from('<I4s', data, 12)
    if kind != b'JSON' or length % 4 or 20 + length > len(data):
        raise ValueError('Invalid GLB JSON section')
    doc = json.loads(data[20:20+length])
    extensions = doc.get('extensions', {})
    declared = set(doc.get('extensionsUsed', [])) | set(doc.get('extensionsRequired', []))
    if 'CESIUM_RTC' not in extensions:
        if 'CESIUM_RTC' in declared:
            raise ValueError('CESIUM_RTC declared without a center')
        return data, [0.0, 0.0, 0.0], None
    rtc = extensions['CESIUM_RTC']
    center = rtc.get('center') if isinstance(rtc, dict) else None
    if (not isinstance(center, list) or len(center) != 3 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in center)):
        raise ValueError('CESIUM_RTC center must have three finite numeric components')
    # Preserve every subsequent chunk byte-for-byte, including embedded images.
    offset = 20 + length
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated GLB chunk header')
        size = struct.unpack_from('<I', data, offset)[0]
        if size % 4 or offset + 8 + size > len(data):
            raise ValueError('Invalid GLB chunk length')
        offset += 8 + size
    del extensions['CESIUM_RTC']
    if not extensions:
        doc.pop('extensions', None)
    for key in ('extensionsUsed', 'extensionsRequired'):
        if key in doc:
            doc[key] = [name for name in doc[key] if name != 'CESIUM_RTC']
            if not doc[key]:
                del doc[key]
    encoded = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode('utf8')
    encoded += b' ' * (-len(encoded) % 4)
    suffix = data[20+length:]
    output = (struct.pack('<4sII', b'glTF', 2, 20 + len(encoded) + len(suffix)) +
              struct.pack('<I4s', len(encoded), b'JSON') + encoded + suffix)
    return output, list(map(float, center)), {
        'extension': 'CESIUM_RTC', 'center_tile_coordinates_m': center,
        'order': 'tile_transform * b3dm_RTC * CESIUM_RTC * Y_up_to_Z_up * node',
        'input_sha256': hashlib.sha256(data).hexdigest(),
        'normalized_sha256': hashlib.sha256(output).hexdigest(),
        'binary_chunks_unchanged': True,
    }
