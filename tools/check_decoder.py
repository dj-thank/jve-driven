"""Real Draco codec test on generated geometry; NOT a public-city test."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import numpy as np
from PIL import Image
import trimesh
from jevdrive.publicworld.compression import decode_geometry
from jevdrive.publicworld.tiles3d import glb_document

root = Path(__file__).resolve().parents[1]
mesh = trimesh.creation.box((10, 20, 10))
image = Image.new('RGB', (16, 16), (70, 100, 130))
mesh.visual = trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), image=image)
original = trimesh.Scene(mesh).export(file_type='glb')
encoded = subprocess.run([shutil.which('node'), str(root/'tools/gltf/decode.mjs'), '--encode-fixture'],
                         input=original, capture_output=True, check=True, timeout=45).stdout
assert 'KHR_draco_mesh_compression' in glb_document(encoded)['extensionsUsed']
os.environ['JEVDRIVE_DECODE_GEOMETRY'] = '1'
decoded, evidence = decode_geometry(encoded, {'KHR_draco_mesh_compression'})
scene = trimesh.load_scene(io.BytesIO(decoded), file_type='glb', process=False)
np.testing.assert_allclose(scene.bounds, mesh.bounds, atol=.01)
assert sum(len(m.faces) for m in scene.geometry.values()) == len(mesh.faces)
assert all(m.visual.kind == 'texture' for m in scene.geometry.values())
assert all(np.isfinite(m.visual.uv).all() for m in scene.geometry.values())
assert 'KHR_draco_mesh_compression' not in glb_document(decoded).get('extensionsUsed', [])
print(json.dumps({'kind':'synthetic_real_codec_roundtrip', 'passed':True, 'evidence':evidence}, indent=2))
