"""Native source-bound Blender rendering; no fabricated Jev/physics evidence."""
from __future__ import annotations
import argparse, hashlib, json, math, sys, time
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def apply_building_finish(material, *, source_only):
    """Optional appearance edit, never part of the imported-material baseline.

    No bpy import is needed for the policy; native shader/socket objects are
    supplied by the caller. Linked inputs are left unchanged. Every modified
    scalar is recorded, including metallic changes that were previously hidden.
    """
    if source_only or material is None or not material.use_nodes:
        return []
    changes=[]
    for shader in material.node_tree.nodes:
        if shader.type!='BSDF_PRINCIPLED':
            continue
        entry={'material':material.name,'shader':shader.name}
        roughness=shader.inputs['Roughness']
        metallic=shader.inputs['Metallic']
        if not roughness.is_linked and roughness.default_value<.1:
            entry.update(old_roughness=float(roughness.default_value),new_roughness=.75)
            roughness.default_value=.75
        if not metallic.is_linked and metallic.default_value!=0:
            entry.update(old_metallic=float(metallic.default_value),new_metallic=0.0)
            metallic.default_value=0.0
        if len(entry)>2:
            changes.append(entry)
    return changes


def record_surface_appearance(material, *, paving_look):
    """Describe colour replacement separately from generic normal/roughness."""
    material['generic_microdetail']=True
    material['source_base_color_preserved']=not paving_look
    # Retain the legacy key but never claim preservation after replacing albedo.
    material['source_ortho_colour_preserved']=not paving_look
    if paving_look:
        material['appearance_override']='Generic CC0 paving, not surveyed Tokyo material'


def new_material(material, seen):
    """Shared mesh materials receive one shader graph, not one per object."""
    identity=material.as_pointer()
    if identity in seen:
        return False
    seen.add(identity)
    return True


def select_output_frames(plan, *, animation):
    """Deduplicate still selections; validate the discrete native frame clock."""
    frames=plan.get('frames')
    fps=plan.get('fps')
    if not isinstance(frames,list) or not frames:
        raise ValueError('Camera plan needs nonempty frames')
    if isinstance(fps,bool) or not isinstance(fps,int) or not 1<=fps<=60:
        raise ValueError('Camera plan fps must be an integer in [1,60]')
    for expected,sample in enumerate(frames,1):
        value=sample.get('frame')
        t=sample.get('time_s')
        if isinstance(value,bool) or not isinstance(value,int) or value!=expected:
            raise ValueError('Camera frames must be contiguous from 1')
        if (isinstance(t,bool) or not isinstance(t,(int,float)) or
                not math.isfinite(t) or abs(t-(expected-1)/fps)>1e-8):
            raise ValueError('Camera frame timestamp differs from render clock')
    if animation:
        return list(range(1,len(frames)+1))
    return sorted({1,max(1,len(frames)//2),len(frames)})


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
    ap.add_argument('--look-preset',choices=['legacy','neutral-daylight'],default='legacy')
    ap.add_argument('--tree-grates',action='store_true',help='Explicit procedural root dressing; not measured infrastructure')
    ap.add_argument('--engine',choices=['EEVEE','CYCLES'],default='EEVEE')
    ap.add_argument('--samples',type=int,default=64)
    ap.add_argument('--animation',action='store_true')
    ap.add_argument('--source-only',action='store_true',
        help='Preserve imported materials; illumination and input derivatives are separate')
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
    output_frames=select_output_frames(plan,animation=args.animation)
    if args.tree_grates and (args.source_only or not args.tree_layer):
        raise ValueError('Tree grates require an authored layer and cannot be source-only')
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import native_lookdev
    code_hashes={str(Path(__file__).resolve()):sha(__file__),str(Path(native_lookdev.__file__).resolve()):sha(native_lookdev.__file__)}
    uv_origin=plan['frames'][0]['xyz'][:2]
    uv_forward=[plan['frames'][0]['target'][i]-uv_origin[i] for i in range(2)]
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
    initial_materials=native_lookdev.material_snapshot(scene)
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
    material_overrides=[]; finished_materials=set()
    for obj in scene.objects:
        if obj.type!='MESH' or not obj.name.startswith('public_building_'): continue
        for mat in obj.data.materials:
            if mat is None or not new_material(mat,finished_materials): continue
            material_overrides.extend(apply_building_finish(mat,source_only=args.source_only))
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
    lookdev=native_lookdev.configure_lighting(scene,args.look_preset)
    surface_prefix='detail_tran_' if args.details else 'public_terrain_'
    terrain_objects=[o for o in scene.objects if o.type=='MESH' and o.name.startswith(surface_prefix)]
    if not terrain_objects: raise ValueError('Rendered terrain not found')
    if not args.source_only:
        detailed_materials=set()
        for obj in terrain_objects:
            uv=obj.data.uv_layers.new(name='DetailMetres')
            for loop in obj.data.loops:
                p=obj.matrix_world @ obj.data.vertices[loop.vertex_index].co
                uv.data[loop.index].uv=(p.x/pack['paving_repeat_m'],p.y/pack['paving_repeat_m']) if args.look_preset=='legacy' else native_lookdev.paving_uv(p.x,p.y,uv_origin,uv_forward,pack['paving_repeat_m'])
            for mat in obj.data.materials:
                if not mat or not mat.use_nodes: continue
                if not new_material(mat,detailed_materials): continue
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
                record_surface_appearance(mat,paving_look=args.paving_look)
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
    grates=native_lookdev.add_tree_grates(scene,visual_layer['trees'],terrain_objects) if args.tree_grates else []
    camera_data=bpy.data.cameras.new('EgoCamera_80deg')
    cam=bpy.data.objects.new('EgoCamera',camera_data); scene.collection.objects.link(cam)
    scene.camera=cam; cam.rotation_mode='QUATERNION'
    camera_data.sensor_fit='HORIZONTAL'; camera_data.sensor_width=36
    camera_data.lens=18/math.tan(math.radians(plan['horizontal_fov_degrees']/2))
    camera_data.clip_start=.05; camera_data.clip_end=4000
    camera_data.dof.use_dof=False
    final_materials=native_lookdev.material_snapshot(scene)
    if args.source_only and initial_materials!=final_materials:
        raise RuntimeError('Imported-material reference changed during scene construction')
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
        for frame_id in output_frames:
            scene.frame_set(frame_id)
            scene.render.filepath=str(out/f'frame_{frame_id:04d}.png')
            bpy.ops.render.render(write_still=True)
    if any(sha(path)!=digest for path,digest in code_hashes.items()):
        raise RuntimeError('Renderer code changed during capture; evidence is invalid')
    (out/'material-audit.json').write_text(json.dumps({'before':initial_materials,'after':final_materials,'unchanged':initial_materials==final_materials},indent=2),encoding='utf8')
    report={'schema':'jevdrive.native-render.v1','blender':bpy.app.version_string,
        'engine':scene.render.engine,'device':device,'samples_requested':args.samples,
        'source_glb_sha256':plan['source_glb_sha256'],'plan_sha256':sha(args.plan),
        'details_glb_sha256':plan.get('details_glb_sha256'),
        'road_appearance_sha256':sha(args.appearance/'appearance.glb') if args.appearance else None,
        'ground_cutout_sha256':sha(args.ground/'ground.glb') if args.ground else None,
        'asset_lock_sha256':sha(assets/'asset-lock.json'),'script_sha256':sha(__file__),
        'frames_rendered':len(output_frames),'rendered_frame_ids':output_frames,
        'coverage_checks':len(residuals),'max_height_residual_m':max(residuals),
        'tree_instances':instances,'source_only':args.source_only,
        'authored_tree_count':len(visual_layer.get('trees',[])),
        'tree_asset_lod':'Poly Haven native LOD1' if args.tree_lod1_assets else 'source glTF',
        'tree_lod_asset_lock_sha256':sha(args.tree_lod1_assets/'asset-lock.json') if args.tree_lod1_assets else None,
        'tree_layer_sha256':sha(args.tree_layer) if args.tree_layer else None,
        'tree_placement_notice':'Authored, not surveyed; visual-only and not traffic actors' if visual_layer else None,
        'assumed_building_finish':material_overrides,
        'generic_paving_albedo':args.paving_look,
        'lookdev':lookdev,'authored_tree_grates':grates,
        'lookdev_helper_sha256':sha(native_lookdev.__file__),
        'renderer_files_unchanged_during_capture':True,
        'imported_materials_unchanged':initial_materials==final_materials,
        'material_audit_sha256':sha(out/'material-audit.json'),
        'paving_orientation':'legacy_world_axes' if args.look_preset=='legacy' else 'camera_route_aligned',
        'authored_grates_notice':'Procedural appearance, not measured Tokyo tree pits; source meshes unchanged' if grates else None,
        'imported_building_materials_preserved':not material_overrides,
        'imported_road_base_color_preserved':not args.paving_look,
        'source_only_scope':'imported material inputs; not measured illumination or unchanged preprocessing',
        'elapsed_s':time.monotonic()-started,'width':int(plan['width']*args.resolution_percent/100),
        'height':int(plan['height']*args.resolution_percent/100),'fps':plan['fps'],
        'jev_calls':0,'physics_simulated':False,'driveable':False,'photorealism_verified':False}
    (out/'render-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__': main()
