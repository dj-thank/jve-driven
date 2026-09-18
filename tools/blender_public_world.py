"""Import a verified public-world visual GLB into Blender. Run in background only.
blender --background --python tools/blender_public_world.py -- --snapshot world/tokyo --out world/tokyo.blend
This script has not been executed in the authoring environment (Blender absent).
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path

def main():
    import bpy
    from mathutils import Vector
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--render',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not bpy.app.background: raise RuntimeError('Run in background; do not replace an open interactive project')
    if args.out.exists(): raise FileExistsError('Refusing to overwrite an existing blend file')
    if args.render and args.render.exists(): raise FileExistsError('Refusing to overwrite an existing render')
    root=args.snapshot.resolve();manifest=json.loads((root/'public-world.json').read_text(encoding='utf8'))
    if manifest.get('stage')!='built' or manifest.get('surface_role')!='visual_only':
        raise ValueError('Expected a completely built visual-only snapshot')
    glb=root/'visual-world.glb'
    if hashlib.sha256(glb.read_bytes()).hexdigest()!=manifest['build']['sha256']:
        raise ValueError('GLB checksum mismatch')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    scene['public_world_manifest']=json.dumps(manifest,ensure_ascii=False)
    scene['driveable']=False;scene['origin_height_reference']='ellipsoid'
    bpy.data.texts.new('PUBLIC_WORLD_PROVENANCE.json').write(json.dumps(manifest,indent=2,ensure_ascii=False))
    points=[o.matrix_world@Vector(v) for o in scene.objects if o.type=='MESH' for v in o.bound_box]
    if not points: raise ValueError('No imported meshes')
    lower=Vector(tuple(min(p[i] for p in points) for i in range(3)))
    upper=Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center=(lower+upper)/2;span=max(upper.x-lower.x,upper.y-lower.y,100)
    # glTF importer already maps Y-up glTF to Z-up Blender. Do NOT apply a second axis rotation.
    cam_data=bpy.data.cameras.new('Inspection_Camera');cam=bpy.data.objects.new('Inspection_Camera',cam_data)
    scene.collection.objects.link(cam);cam.location=center+Vector((span*.65,-span*.9,span*.65))
    cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler();cam_data.lens=40
    cam_data.clip_end=max(10000,span*10);scene.camera=cam
    light_data=bpy.data.lights.new('Inspection_Sun','SUN');light_data.energy=2
    sun=bpy.data.objects.new('Inspection_Sun',light_data);scene.collection.objects.link(sun)
    sun.rotation_euler=(.5,-.3,-.5)
    world=bpy.data.worlds.new('Inspection_Environment');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.65;scene.world=world
    scene.render.engine='CYCLES';scene.cycles.samples=64
    scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene['lighting_note']='Inspection lighting, not measured conditions. Source imagery can contain baked shadows.'
    bpy.ops.file.pack_all();args.out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out.resolve()))
    if args.render:
        args.render.parent.mkdir(parents=True,exist_ok=True)
        scene.render.filepath=str(args.render.resolve());scene.render.image_settings.file_format='PNG'
        bpy.ops.render.render(write_still=True)
    print(json.dumps({'blend':str(args.out),'driveable':False,'source_glb_sha256':manifest['build']['sha256']}))

if __name__=='__main__': main()
