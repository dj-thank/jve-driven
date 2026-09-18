"""Native source-bound Blender rendering; no fabricated Jev/physics evidence."""
from __future__ import annotations
import argparse, hashlib, json, math, sys, time
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    import bpy
    from mathutils import Vector
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot',type=Path,required=True)
    ap.add_argument('--assets',type=Path,required=True)
    ap.add_argument('--plan',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--tree-layer',type=Path,help='Explicit authored appearance, never mapped tree truth')
    ap.add_argument('--tree-lod1-assets',type=Path,help='Hash-locked Poly Haven native LOD1 pack')
    ap.add_argument('--details',type=Path)
    ap.add_argument('--ground',type=Path)
    ap.add_argument('--appearance',type=Path)
    ap.add_argument('--engine',choices=['EEVEE','CYCLES'],default='EEVEE')
    ap.add_argument('--samples',type=int,default=64)
    ap.add_argument('--animation',action='store_true')
    ap.add_argument('--source-only',action='store_true')
    ap.add_argument('--paving-look',action='store_true',help='Generic CC0 paving appearance; not a local survey')
    ap.add_argument('--resolution-percent',type=int,default=100)
    args=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not bpy.app.background: raise RuntimeError('Use background mode to protect open projects')
    if args.source_only and args.paving_look: raise ValueError('Source-only and generic paving are distinct modes')
    if args.out.exists(): raise FileExistsError('Choose a new output directory')
    if not 16<=args.samples<=512 or not 25<=args.resolution_percent<=100:
        raise ValueError('Render budget outside supported range')
    snapshot=args.snapshot.resolve(); assets=args.assets.resolve()
    plan=json.loads(args.plan.read_text(encoding='utf8'))
    visual_layer={}
    if args.tree_layer:
        if args.source_only: raise ValueError('Source-only cannot add authored trees')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
        from jevdrive.visual_enrichment import validate_tree_layer
        visual_layer=json.loads(args.tree_layer.read_text(encoding='utf8'))
        validate_tree_layer(visual_layer,plan,sha(args.plan))
    pack=json.loads((assets/'asset-lock.json').read_text(encoding='utf8'))
    if sha(snapshot/'visual-world.glb')!=plan['source_glb_sha256']:
        raise ValueError('Plan and visual-world GLB differ')
    if sha(snapshot/'source-lock.json')!=plan['source_lock_sha256']:
        raise ValueError('Source lock differs from the camera plan')
    for record in pack['resources']:
        path=(assets/record['path']).resolve()
        if not path.is_relative_to(assets) or sha(path)!=record['sha256']:
            raise ValueError('Appearance asset checksum mismatch')
    args.out.mkdir(parents=True); out=args.out.resolve(); started=time.monotonic()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(snapshot/'visual-world.glb'))
    if args.details:
        if not args.ground: raise ValueError('LOD3 roads require the terrain cutout')
        detail=args.details.resolve(); ground=args.ground.resolve()
        if sha(detail/'details.glb')!=plan.get('details_glb_sha256'):
            raise ValueError('Plan and detail GLB disagree')
        if sha(detail/'details-manifest.json')!=plan.get('details_manifest_sha256'):
            raise ValueError('Detail metadata changed')
        gm=json.loads((ground/'ground-manifest.json').read_text(encoding='utf8'))
        if (gm['source_glb_sha256']!=plan['source_glb_sha256'] or
            gm['details_glb_sha256']!=plan['details_glb_sha256'] or
            gm['glb_sha256']!=sha(ground/'ground.glb')):
            raise ValueError('Cutout/source identity mismatch')
        for obj in bpy.context.scene.objects:
            if obj.name.startswith('public_terrain_'): obj.hide_render=True
        bpy.ops.import_scene.gltf(filepath=str(ground/'ground.glb'))
        if args.appearance:
            appearance=args.appearance.resolve()
            am=json.loads((appearance/'appearance-manifest.json').read_text(encoding='utf8'))
            if (am['details_glb_sha256']!=plan['details_glb_sha256'] or
                am['source_glb_sha256']!=plan['source_glb_sha256'] or
                sha(appearance/'appearance.glb')!=am['glb_sha256']):
                raise ValueError('Road appearance/source identity mismatch')
            bpy.ops.import_scene.gltf(filepath=str(appearance/'appearance.glb'))
        else:
            bpy.ops.import_scene.gltf(filepath=str(detail/'details.glb'))
    elif 'details_glb_sha256' in plan:
        raise ValueError('Plan needs its LOD3 detail geometry')
    scene=bpy.context.scene; scene.unit_settings.system='METRIC'
    scene.render.engine='CYCLES' if args.engine=='CYCLES' else 'BLENDER_EEVEE'
    device='CPU' if args.engine=='CYCLES' else 'EEVEE graphics device'
    if args.engine=='CYCLES':
        scene.cycles.samples=args.samples; scene.cycles.use_denoising=True
        scene.cycles.max_bounces=8; scene.cycles.seed=20260918
        scene.cycles.device='CPU'
    else:
        if hasattr(scene.eevee,'taa_render_samples'): scene.eevee.taa_render_samples=args.samples
        if hasattr(scene.eevee,'use_raytracing'): scene.eevee.use_raytracing=True
    scene.render.resolution_x=plan['width']; scene.render.resolution_y=plan['height']
    scene.render.resolution_percentage=args.resolution_percent
    scene.render.fps=plan['fps']; scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.view_settings.view_transform='AgX'; scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=0.8
    material_overrides=[]
    for obj in scene.objects:
        if obj.type!='MESH' or not obj.name.startswith('public_building_'): continue
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes: continue
            for shader in mat.node_tree.nodes:
                if shader.type!='BSDF_PRINCIPLED': continue
                r=shader.inputs['Roughness']; metal=shader.inputs['Metallic']
                if not r.is_linked and r.default_value<.1:
                    material_overrides.append({'material':mat.name,'old_roughness':r.default_value,'new_roughness':.75})
                    r.default_value=.75
                if not metal.is_linked: metal.default_value=0
    scene['assumed_building_finish']=json.dumps(material_overrides)
    world=bpy.data.worlds.new('CC0_Sky_Not_Local_Weather'); world.use_nodes=True
    scene.world=world; nodes=world.node_tree.nodes; links=world.node_tree.links
    env=nodes.new('ShaderNodeTexEnvironment'); env.image=bpy.data.images.load(str(assets/pack['sky']))
    links.new(env.outputs['Color'],nodes.get('Background').inputs['Color'])
    nodes.get('Background').inputs['Strength'].default_value=0.95
    sun_data=bpy.data.lights.new('Art_Direction_Sun','SUN'); sun_data.energy=1.4
    sun_data.angle=math.radians(6)
    sun=bpy.data.objects.new('Art_Direction_Sun',sun_data); scene.collection.objects.link(sun)
    sun.rotation_euler=(math.radians(25),math.radians(-15),math.radians(30))
    surface_prefix='detail_tran_' if args.details else 'public_terrain_'
    terrain_objects=[o for o in scene.objects if o.type=='MESH' and o.name.startswith(surface_prefix)]
    if not terrain_objects: raise ValueError('Rendered terrain not found')
    if not args.source_only:
        for obj in terrain_objects:
            uv=obj.data.uv_layers.new(name='DetailMetres')
            for loop in obj.data.loops:
                p=obj.matrix_world @ obj.data.vertices[loop.vertex_index].co
                uv.data[loop.index].uv=(p.x/pack['paving_repeat_m'],p.y/pack['paving_repeat_m'])
            for mat in obj.data.materials:
                if not mat or not mat.use_nodes: continue
                mat['generic_microdetail']=True; mat['source_ortho_colour_preserved']=True
                nt=mat.node_tree; bs=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None)
                if bs is None: continue
                coords=nt.nodes.new('ShaderNodeUVMap'); coords.uv_map='DetailMetres'
                if args.paving_look:
                    if plan['osm_tags'].get('surface')!='paving_stones':
                        raise ValueError('Generic paving requires an explicit OSM paving_stones tag')
                    if 'albedo' not in pack: raise ValueError('Asset pack has no photographed paving albedo')
                    albedo=nt.nodes.new('ShaderNodeTexImage')
                    albedo.image=bpy.data.images.load(str(assets/pack['albedo']),check_existing=True)
                    nt.links.new(coords.outputs['UV'],albedo.inputs['Vector'])
                    for link in list(bs.inputs['Base Color'].links): nt.links.remove(link)
                    nt.links.new(albedo.outputs['Color'],bs.inputs['Base Color'])
                    mat['appearance_override']='Generic CC0 paving, not surveyed Tokyo material'
                normal=nt.nodes.new('ShaderNodeTexImage')
                normal.image=bpy.data.images.load(str(assets/pack['normal']),check_existing=True)
                normal.image.colorspace_settings.name='Non-Color'
                nt.links.new(coords.outputs['UV'],normal.inputs['Vector'])
                bump=nt.nodes.new('ShaderNodeNormalMap'); bump.uv_map='DetailMetres'
                bump.inputs['Strength'].default_value=0.08
                nt.links.new(normal.outputs['Color'],bump.inputs['Color'])
                nt.links.new(bump.outputs['Normal'],bs.inputs['Normal'])
                rough=nt.nodes.new('ShaderNodeTexImage')
                rough.image=bpy.data.images.load(str(assets/pack['roughness']),check_existing=True)
                rough.image.colorspace_settings.name='Non-Color'
                nt.links.new(coords.outputs['UV'],rough.inputs['Vector'])
                remap=nt.nodes.new('ShaderNodeMapRange')
                remap.inputs['To Min'].default_value=0.65; remap.inputs['To Max'].default_value=0.90
                nt.links.new(rough.outputs['Color'],remap.inputs['Value'])
                nt.links.new(remap.outputs['Result'],bs.inputs['Roughness'])
    instances=[]
    placements=plan['trees']+visual_layer.get('trees',[])
    if not args.source_only and placements:
        before=set(bpy.data.objects)
        if args.tree_lod1_assets:
            lodroot=args.tree_lod1_assets.resolve()
            lodlock=json.loads((lodroot/'asset-lock.json').read_text(encoding='utf8'))
            for record in lodlock['files']:
                path=(lodroot/record['path']).resolve()
                if not path.is_relative_to(lodroot) or sha(path)!=record['sha256']:
                    raise ValueError('Native LOD asset integrity failure')
            with bpy.data.libraries.load(str(lodroot/'tree_small_02/tree.blend'),link=False) as (source,target):
                if 'tree_small_02_LOD1' not in source.objects: raise ValueError('Native tree LOD1 unavailable')
                target.objects=['tree_small_02_LOD1']
            textures={Path(r['path']).name:lodroot/r['path'] for r in lodlock['files'] if r['path'].startswith('tree_small_02/textures/')}
            for image in bpy.data.images:
                name=Path(image.filepath.replace('\\','/')).name
                if name in textures:
                    image.filepath=str(textures[name]); image.reload()
        else:
            bpy.ops.import_scene.gltf(filepath=str(assets/pack['tree']))
        tree_objects=set(bpy.data.objects)-before
        collection=bpy.data.collections.new('CC0_Tree_Template_Not_Surveyed')
        for obj in tree_objects:
            for owner in list(obj.users_collection): owner.objects.unlink(obj)
            collection.objects.link(obj)
        vertices=[o.matrix_world @ Vector(v) for o in tree_objects if o.type=='MESH' for v in o.bound_box]
        if not vertices: raise ValueError('Tree asset has no mesh bounds')
        minimum=min(v.z for v in vertices); maximum=max(v.z for v in vertices)
        if maximum-minimum < .1: raise ValueError('Tree asset has no usable height')
        collection.instance_offset.z=minimum
        for item in placements:
            tree_id=item.get('osm_node_id') or item['id']
            instance=bpy.data.objects.new(('OSM_tree_' if item.get('osm_node_id') else 'AUTHORED_tree_')+tree_id,None)
            instance.instance_type='COLLECTION'; instance.instance_collection=collection
            instance.location=item['xyz']
            angle=int(item['osm_node_id'])%360 if item.get('osm_node_id') else item['rotation_degrees']
            instance.rotation_euler.z=math.radians(angle)
            if item.get('height_m'):
                scale=item['height_m']/(maximum-minimum)
                instance.scale=(scale,scale,scale)
            if not item.get('osm_node_id'):
                hits=[]
                for ground in terrain_objects:
                    inv=ground.matrix_world.inverted()
                    hit,pos,_,_=ground.ray_cast(inv @ Vector((item['xyz'][0],item['xyz'][1],1000)),(inv.to_3x3() @ Vector((0,0,-1))).normalized())
                    if hit: hits.append((ground.matrix_world @ pos).z)
                if not hits or abs(max(hits)-item['xyz'][2])>.03:
                    raise ValueError('Authored tree is not on its verified Blender source surface')
            instance['provenance']=json.dumps(item); scene.collection.objects.link(instance)
            instances.append(instance.name)
    camera_data=bpy.data.cameras.new('EgoCamera_80deg')
    cam=bpy.data.objects.new('EgoCamera',camera_data); scene.collection.objects.link(cam)
    scene.camera=cam; cam.rotation_mode='QUATERNION'
    camera_data.sensor_fit='HORIZONTAL'; camera_data.sensor_width=36
    camera_data.lens=18/math.tan(math.radians(plan['horizontal_fov_degrees']/2))
    camera_data.clip_start=.05; camera_data.clip_end=4000
    camera_data.dof.use_dof=False
    residuals=[]
    for sample in plan['frames']:
        cam.location=sample['xyz']
        cam.rotation_quaternion=(Vector(sample['target'])-cam.location).to_track_quat('-Z','Y')
        cam.keyframe_insert(data_path='location',frame=sample['frame'])
        cam.keyframe_insert(data_path='rotation_quaternion',frame=sample['frame'])
        heights=[]
        for ground in terrain_objects:
            inv=ground.matrix_world.inverted()
            origin=inv @ Vector((cam.location.x,cam.location.y,1000))
            direction=(inv.to_3x3() @ Vector((0,0,-1))).normalized()
            hit, location, _, _ = ground.ray_cast(origin,direction)
            if hit: heights.append((ground.matrix_world @ location).z)
        if not heights: raise RuntimeError('Camera is outside Blender rendered terrain')
        error=abs(max(heights)-sample.get('surface_z',sample['terrain_z'])); residuals.append(error)
        if error>.03: raise RuntimeError('Blender terrain and planned height disagree')
    scene.frame_start=1; scene.frame_end=len(plan['frames'])
    scene['visual_tree_layer']=json.dumps(visual_layer)
    scene['visual_only']=True; scene['jev_calls']=0
    scene['camera_plan']=json.dumps(plan,ensure_ascii=False)
    scene['source_and_asset_provenance']=json.dumps(pack)
    bpy.data.texts.new('CAMERA_PLAN.json').write(json.dumps(plan,indent=2,ensure_ascii=False))
    bpy.data.texts.new('ASSET_LOCK.json').write(json.dumps(pack,indent=2))
    scene.frame_set(1)
    (out/'frames').mkdir()
    scene.render.filepath=str(out/'frames/frame_')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    if args.animation:
        bpy.ops.render.render(animation=True)
    else:
        for frame_id in (1, len(plan['frames'])//2, len(plan['frames'])):
            scene.frame_set(frame_id)
            scene.render.filepath=str(out/f'frame_{frame_id:04d}.png')
            bpy.ops.render.render(write_still=True)
    report={'schema':'jevdrive.native-render.v1','blender':bpy.app.version_string,
        'engine':scene.render.engine,'device':device,'samples_requested':args.samples,
        'source_glb_sha256':plan['source_glb_sha256'],'plan_sha256':sha(args.plan),
        'details_glb_sha256':plan.get('details_glb_sha256'),
        'road_appearance_sha256':sha(args.appearance/'appearance.glb') if args.appearance else None,
        'ground_cutout_sha256':sha(args.ground/'ground.glb') if args.ground else None,
        'asset_lock_sha256':sha(assets/'asset-lock.json'),'script_sha256':sha(__file__),
        'frames_rendered':len(plan['frames']) if args.animation else 3,
        'coverage_checks':len(residuals),'max_height_residual_m':max(residuals),
        'tree_instances':instances,'source_only':args.source_only,
        'authored_tree_count':len(visual_layer.get('trees',[])),
        'tree_asset_lod':'Poly Haven native LOD1' if args.tree_lod1_assets else 'source glTF',
        'tree_lod_asset_lock_sha256':sha(args.tree_lod1_assets/'asset-lock.json') if args.tree_lod1_assets else None,
        'tree_layer_sha256':sha(args.tree_layer) if args.tree_layer else None,
        'tree_placement_notice':'Authored, not surveyed; visual-only and not traffic actors' if visual_layer else None,
        'assumed_building_finish':material_overrides,
        'generic_paving_albedo':args.paving_look,
        'elapsed_s':time.monotonic()-started,'width':int(plan['width']*args.resolution_percent/100),
        'height':int(plan['height']*args.resolution_percent/100),'fps':plan['fps'],
        'jev_calls':0,'physics_simulated':False,'driveable':False,'photorealism_verified':False}
    (out/'render-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__': main()
