"""Subprocess contract fixtures. Real codec round-trip runs in public-world CI."""
import io
import json
import struct
import subprocess
from types import SimpleNamespace
import numpy as np
import pytest
import trimesh
from test_public_world import sample_glb, FRAME
from jevdrive.publicworld import compression
from jevdrive.publicworld.tiles3d import glb_document, load_geometry


def amended_glb(extension='KHR_draco_mesh_compression', external=False):
    original = sample_glb()
    n = struct.unpack_from('<I', original, 12)[0]
    doc = glb_document(original)
    doc['extensionsUsed'] = [extension]
    if external:
        doc['images'] = [{'uri': 'https://unapproved.example/texture.png'}]
    encoded = json.dumps(doc).encode()
    encoded += b' ' * (-len(encoded) % 4)
    rest = original[20+n:]
    return struct.pack('<4sII', b'glTF', 2, 20+len(encoded)+len(rest)) + struct.pack('<I4s', len(encoded), b'JSON') + encoded + rest


def test_decode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv('JEVDRIVE_DECODE_GEOMETRY', raising=False)
    with pytest.raises(RuntimeError, match='explicit opt-in'):
        compression.decode_geometry(sample_glb(), {'KHR_draco_mesh_compression'})


def test_wrong_extension_not_silently_decoded():
    with pytest.raises(ValueError, match='Only Draco/meshopt'):
        compression.decode_geometry(sample_glb(), {'KHR_texture_basisu'})


def test_decode_process_is_bounded_and_does_not_inherit_credentials(monkeypatch):
    monkeypatch.setenv('JEVDRIVE_DECODE_GEOMETRY', '1')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setenv('NODE_OPTIONS', '--inspect')
    monkeypatch.setattr(compression.shutil, 'which', lambda _: '/usr/bin/node')
    def invoke(args, **kwargs):
        assert kwargs['timeout'] == 45 and kwargs['input'][:4] == b'glTF'
        assert 'TYPESAFE_API_KEY' not in kwargs['env'] and 'NODE_OPTIONS' not in kwargs['env']
        assert not kwargs.get('shell', False)
        assert '--max-old-space-size=512' in args
        return SimpleNamespace(returncode=0, stdout=sample_glb())
    monkeypatch.setattr(compression.subprocess, 'run', invoke)
    decoded, evidence = compression.decode_geometry(amended_glb(), {'KHR_draco_mesh_compression'})
    assert decoded[:4] == b'glTF' and len(evidence['input_sha256']) == 64
    assert not evidence['simplified'] and not evidence['textures_reencoded']


@pytest.mark.parametrize('result', [SimpleNamespace(returncode=2, stdout=b''), SimpleNamespace(returncode=0, stdout=b'bad')])
def test_bad_decoder_output_rejected(monkeypatch, result):
    monkeypatch.setenv('JEVDRIVE_DECODE_GEOMETRY', '1')
    monkeypatch.setattr(compression.shutil, 'which', lambda _: '/usr/bin/node')
    monkeypatch.setattr(compression.subprocess, 'run', lambda *a, **kw: result)
    with pytest.raises((RuntimeError, ValueError)):
        compression.decode_geometry(amended_glb(), {'KHR_draco_mesh_compression'})


def test_decoder_deadline(monkeypatch):
    monkeypatch.setenv('JEVDRIVE_DECODE_GEOMETRY', '1')
    monkeypatch.setattr(compression.shutil, 'which', lambda _: '/usr/bin/node')
    def timed_out(*a, **kw):
        raise subprocess.TimeoutExpired('node', 45)
    monkeypatch.setattr(compression.subprocess, 'run', timed_out)
    with pytest.raises(RuntimeError, match='deadline'):
        compression.decode_geometry(amended_glb(), {'KHR_draco_mesh_compression'})


def test_external_texture_rejected_before_decoder(monkeypatch):
    def forbidden(*a):
        raise AssertionError('Do not start decoder on external resources')
    monkeypatch.setattr('jevdrive.publicworld.tiles3d.decode_geometry', forbidden)
    with pytest.raises(RuntimeError, match='External glTF'):
        load_geometry(amended_glb(external=True), np.eye(4), FRAME, 'contract-fixture')


def test_basis_texture_remains_unsupported():
    with pytest.raises(RuntimeError, match='BasisU'):
        load_geometry(amended_glb('KHR_texture_basisu'), np.eye(4), FRAME, 'contract-fixture')


def test_decoder_must_remove_compression(monkeypatch):
    monkeypatch.setattr('jevdrive.publicworld.tiles3d.decode_geometry', lambda data, ext: (data, {}))
    with pytest.raises(ValueError, match='did not remove'):
        load_geometry(amended_glb(), np.eye(4), FRAME, 'contract-fixture')


def test_decoder_evidence_survives_glb_export(monkeypatch):
    evidence = {'input_sha256': 'synthetic-contract-fixture', 'simplified': False}
    monkeypatch.setattr('jevdrive.publicworld.tiles3d.decode_geometry', lambda data, ext: (sample_glb(), evidence))
    scene = load_geometry(amended_glb(), np.linalg.inv(FRAME.ecef_to_enu), FRAME, 'contract-fixture')
    exported = scene.export(file_type='glb')
    loaded = trimesh.load_scene(io.BytesIO(exported), file_type='glb')
    assert all(mesh.metadata['geometry_decoder'] == evidence for mesh in loaded.geometry.values())
