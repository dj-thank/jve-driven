"""Synthetic coordinate regressions; no claim of surveyed Tokyo accuracy."""
import io
import json
import struct
import numpy as np
import pytest
import trimesh
from test_public_world import sample_glb, b3dm, FRAME
from jevdrive.publicworld.rtc import extract_cesium_rtc
from jevdrive.publicworld.tiles3d import glb_document, load_geometry
from jevdrive.publicworld.geo import GLTF_TO_ZUP, ENU_TO_GLTF


def with_rtc(data, center):
    n = struct.unpack_from('<I', data, 12)[0]
    doc = glb_document(data)
    doc.setdefault('extensions', {})['CESIUM_RTC'] = {'center': center}
    doc.setdefault('extensionsUsed', []).append('CESIUM_RTC')
    doc.setdefault('extensionsRequired', []).append('CESIUM_RTC')
    encoded = json.dumps(doc).encode()
    encoded += b' ' * (-len(encoded) % 4)
    suffix = data[20+n:]
    return struct.pack('<4sII', b'glTF', 2, 20+len(encoded)+len(suffix)) + struct.pack('<I4s', len(encoded), b'JSON') + encoded + suffix


def test_no_extension_is_byte_identical():
    data = sample_glb()
    out, center, evidence = extract_cesium_rtc(data)
    assert out == data and center == [0, 0, 0] and evidence is None


def test_binary_chunks_and_other_extensions_preserved():
    data = with_rtc(sample_glb(), [123, 456, 789])
    out, center, evidence = extract_cesium_rtc(data)
    source_n = struct.unpack_from('<I', data, 12)[0]
    output_n = struct.unpack_from('<I', out, 12)[0]
    assert out[20+output_n:] == data[20+source_n:]
    assert center == [123, 456, 789] and evidence['binary_chunks_unchanged']
    assert 'CESIUM_RTC' not in str(glb_document(out))
    loaded = trimesh.load_scene(io.BytesIO(out), file_type='glb')
    assert all(m.visual.kind == 'texture' for m in loaded.geometry.values())


@pytest.mark.parametrize('center', [None, [1, 2], [1, 2, 3, 4], [True, 2, 3], ['1', 2, 3], [float('nan'), 0, 0], [0, 0, float('inf')]])
def test_malformed_center_rejected(center):
    with pytest.raises(ValueError, match='center'):
        extract_cesium_rtc(with_rtc(sample_glb(), center))


def test_gltf_rtc_is_added_after_axis_conversion():
    scene = load_geometry(with_rtc(sample_glb(), [10, 20, 30]),
                          np.linalg.inv(FRAME.ecef_to_enu), FRAME, 'fixture')
    np.testing.assert_allclose(scene.centroid, [10, 20, 85], atol=1e-6)


def test_both_rtc_translations_are_composed_once():
    data = b3dm(with_rtc(sample_glb(), [10, 20, 30]), rtc=(1, 2, 3))
    scene = load_geometry(data, np.linalg.inv(FRAME.ecef_to_enu), FRAME, 'fixture')
    np.testing.assert_allclose(scene.centroid, [11, 22, 88], atol=1e-6)


def test_ecef_origin_and_orientation_recover_local_height():
    # A glTF relative to an ECEF center with its correct baked orientation.
    enu_to_ecef = np.linalg.inv(FRAME.ecef_to_enu)
    center = enu_to_ecef[:3, 3].tolist()
    rotation = enu_to_ecef.copy()
    rotation[:3, 3] = 0
    source = trimesh.load_scene(io.BytesIO(sample_glb()), file_type='glb')
    source.apply_transform(ENU_TO_GLTF @ rotation @ GLTF_TO_ZUP)
    data = with_rtc(source.export(file_type='glb'), center)
    scene = load_geometry(data, np.eye(4), FRAME, 'ecef-fixture')
    np.testing.assert_allclose(scene.centroid, [0, 0, 55], atol=1e-5)
    np.testing.assert_allclose(scene.bounds[:, 2], [45, 65], atol=1e-5)


def test_rtc_is_removed_before_geometry_decoder(monkeypatch):
    from test_geometry_compression import amended_glb
    def decoder(data, extensions):
        assert 'CESIUM_RTC' not in str(glb_document(data))
        return sample_glb(), {'input_sha256': 'fixture'}
    monkeypatch.setattr('jevdrive.publicworld.tiles3d.decode_geometry', decoder)
    scene = load_geometry(with_rtc(amended_glb(), [10, 20, 30]),
                          np.linalg.inv(FRAME.ecef_to_enu), FRAME, 'fixture')
    np.testing.assert_allclose(scene.centroid, [10, 20, 85], atol=1e-6)
    assert all(m.metadata['rtc_normalization']['center_tile_coordinates_m'] == [10, 20, 30]
               for m in scene.geometry.values())
