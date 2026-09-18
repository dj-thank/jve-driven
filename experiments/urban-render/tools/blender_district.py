"""Import generated district.glb, bake camera/actor animation and optionally render.

Use Blender --background --python-exit-code 2 --python tools/blender_district.py --
--scene output/district-final --out output/blender-review [--render-stills]

This entry point is exercised separately; consult render-report.json for native execution evidence.
Existing workspaces and source city datasets are never opened or overwritten.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from urban_district.runtime import RuntimeRoad, instance_transform, light_state


def main():
    import bpy
    from mathutils import Matrix,Vector
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene',type=Path,default=ROOT/'output/district-final')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--engine',choices=['EEVEE','CYCLES'],default='EEVEE')
    p.add_argument('--samples',type=int,default=96)
    p.add_argument('--render-stills',action='store_true')
    p.add_argument('--frame',type=int,default=0,help='Render one 1-based output frame')
    p.add_argument('--resolution-percent',type=int,default=100)
    p.add_argument('--animation',action='store_true')
    p.add_argument('--detail-views',action='store_true',help='Render explicitly labelled vehicle and entrance inspection views at frame 1')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not bpy.app.background:raise RuntimeError('Background mode required; no open project will be replaced')
    if a.out.exists():raise FileExistsError('Output must be a new directory')
    if not 1<=a.samples<=1024:raise ValueError('Samples outside [1,1024]')
    if not 10<=a.resolution_percent<=100:raise ValueError('Resolution percent outside [10,100]')
    root=a.scene.resolve();meta=json.loads((root/'scene.json').read_text(encoding='utf8'))
    if meta.get('schema')!='urban.scene.v1' or meta.get('driveable') or meta.get('geographic_replica'):raise ValueError('Not an authored visual study')
    if hashlib.sha256((root/'district.glb').read_bytes()).hexdigest()!=meta['glb_sha256']:raise ValueError('GLB hash mismatch')
    a.out.mkdir(parents=True);out=a.out.resolve();t0=time.monotonic()
    report={'schema':'urban.blender-render.v1','completed':False,'blender':bpy.app.version_string,
        'source_glb_sha256':meta['glb_sha256'],'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'jev_calls':0,'physics_simulated':False,'geographic_replica':False,'authored_ground_not_geodetic':True,'rendered_frames':[]}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(root/'district.glb'))
        scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
        available={e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items}
        engine='CYCLES' if a.engine=='CYCLES' else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in available else 'BLENDER_EEVEE_NEXT')
        scene.render.engine=engine
        if engine=='CYCLES':scene.cycles.samples=a.samples;scene.cycles.device='CPU';scene.cycles.use_denoising=True
        elif hasattr(scene,'eevee') and hasattr(scene.eevee,'taa_render_samples'):scene.eevee.taa_render_samples=a.samples
        scene.render.resolution_x=meta['config']['camera']['width'];scene.render.resolution_y=meta['config']['camera']['height'];scene.render.resolution_percentage=a.resolution_percent
        scene.render.fps=meta['config']['camera']['fps'];scene.render.image_settings.file_format='PNG'
        scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.7
        # Original analytic daylight, not a measured sun/sky at the target location.
        world=bpy.data.worlds.new('Authored_Daylight');world.use_nodes=True;scene.world=world
        world.node_tree.nodes['Background'].inputs[0].default_value=(.52,.65,.78,1)
        world.node_tree.nodes['Background'].inputs[1].default_value=.35
        report['environment']='original analytic'
        if meta.get('environment'):
            e=meta['environment'];hp=(root/e['file']).resolve()
            if not hp.is_relative_to(root) or hashlib.sha256(hp.read_bytes()).hexdigest()!=e['sha256']:
                raise ValueError('Environment integrity failed')
            sky=world.node_tree.nodes.new('ShaderNodeTexEnvironment');sky.image=bpy.data.images.load(str(hp))
            world.node_tree.links.new(sky.outputs['Color'],world.node_tree.nodes['Background'].inputs['Color'])
            world.node_tree.nodes['Background'].inputs[1].default_value=1.1
            report['environment']=e
        scene.render.threads_mode='FIXED';scene.render.threads=4
        scene.cycles.max_bounces=6;scene.cycles.transparent_max_bounces=8
        # Source GLB carries actual transmission and clearcoat. Do not apply VTK's opacity approximation.
        report['material_policy']='glTF original channels; no global roughness/metallic rewrite'

        sun_data=bpy.data.lights.new('Assumed_Sun','SUN');sun_data.energy=3.0;sun_data.angle=math.radians(1.5)
        sun=bpy.data.objects.new('Assumed_Sun',sun_data);scene.collection.objects.link(sun);sun.rotation_euler=(.18,-.07,-.35)
        cam_data=bpy.data.cameras.new('EgoCamera');cam=bpy.data.objects.new('EgoCamera',cam_data);scene.collection.objects.link(cam);scene.camera=cam
        cam_data.sensor_width=36;cam_data.sensor_fit='HORIZONTAL';cam_data.lens=36/(2*math.tan(math.radians(meta['config']['camera']['horizontal_fov_degrees']/2)))
        cam_data.clip_start=.06;cam_data.clip_end=1800
        byid={i['id']:i for i in meta['instances']};objects={}
        for obj in scene.objects:
            ident=obj.name.split('::')[0]
            if ident in byid:objects.setdefault(ident,[]).append(obj)
        missing=[i['id'] for i in meta['instances'] if i['motion'] and i['id'] not in objects]
        if missing:raise RuntimeError('Imported animated objects missing: '+','.join(missing[:5]))
        original_world={obj.name:obj.matrix_world.copy() for obs in objects.values() for obj in obs}
        road=RuntimeRoad(meta['route_anchor']);scene.frame_start=1;scene.frame_end=len(meta['camera_frames'])
        # All integer output frames are explicitly keyed, without dependence on FCurve API versions.
        for f in meta['camera_frames']:
            frame=f['frame'];t=f['time_s'];cam.location=f['position']
            cam.rotation_euler=(Vector(f['target'])-cam.location).to_track_quat('-Z','Y').to_euler()
            cam.keyframe_insert(data_path='location',frame=frame);cam.keyframe_insert(data_path='rotation_euler',frame=frame)
            for ident,obs in objects.items():
                inst=byid[ident]
                if not inst['motion']:continue
                for obj in obs:
                    delta=Matrix(instance_transform(inst,t,meta,road)) @ Matrix(inst['matrix']).inverted()
                    obj.matrix_world=delta @ original_world[obj.name]
                    obj.keyframe_insert(data_path='location',frame=frame);obj.keyframe_insert(data_path='rotation_euler',frame=frame)
            # Materials are shared intentionally by traffic channel; no physical signal claim.
            for material,kind in [('signal_green','signal'),('signal_red_off','signal'),('signal_red','ped_signal'),('ped_green_off','ped_signal')]:
                mat=bpy.data.materials.get(material)
                if not mat or not mat.use_nodes:continue
                node=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
                if node is None:continue
                d=meta['materials'][light_state(material,kind,t,meta['config'])]
                node.inputs['Base Color'].default_value=tuple(v/255 for v in d['rgb'])+(1.,)
                node.inputs['Base Color'].keyframe_insert(data_path='default_value',frame=frame)
                if 'Emission Color' in node.inputs:
                    node.inputs['Emission Color'].default_value=tuple(d['emission'] or [0,0,0])+(1.,)
                    node.inputs['Emission Color'].keyframe_insert(data_path='default_value',frame=frame)
        scene.frame_set(1);scene['scene_provenance']='Authored district anchored in XY to saved OSM road. No PLATEAU geometry included. No Jev or physics.'
        bpy.data.texts.new('PROVENANCE.json').write(json.dumps(meta,ensure_ascii=False,indent=2))
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'district.blend'))
        frames=out/'frames';frames.mkdir()
        if a.frame<0 or a.frame>scene.frame_end:raise ValueError('Requested frame out of range')
        selected=[a.frame] if a.frame else range(1,scene.frame_end+1) if a.animation else sorted({1,(scene.frame_end+1)//2,scene.frame_end}) if a.render_stills else []
        for frame in selected:
            scene.frame_set(frame);path=frames/f'frame_{frame:04d}.png';scene.render.filepath=str(path)
            bpy.ops.render.render(write_still=True)
            report['rendered_frames'].append({'frame':frame,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if a.detail_views:
            scene.frame_set(1)
            view_specs=[]
            leader=next(i for i in meta['instances'] if i.get('source_asset')=='toy_car' and i.get('motion'))
            m=Matrix(instance_transform(leader,0,meta,road));center=m.translation
            forward=m.to_3x3() @ Vector((0,1,0));right=m.to_3x3() @ Vector((1,0,0))
            view_specs.append(('vehicle',center-forward*6+right*3+Vector((0,0,1.65)),center+Vector((0,0,.85))))
            entry=next(i for i in meta['instances'] if i['prototype'].startswith('premium_entry'))
            m=Matrix(entry['matrix']);center=m.translation
            view_specs.append(('entrance',center+m.to_3x3()@Vector((3,-9,1.6)),center+Vector((0,0,1.8))))
            report['detail_views']=[]
            inspection=bpy.data.objects.new('InspectionCamera',cam_data.copy())
            scene.collection.objects.link(inspection);scene.camera=inspection
            for label,position,target in view_specs:
                inspection.location=position;inspection.rotation_euler=(target-position).to_track_quat('-Z','Y').to_euler()
                if inspection.animation_data is not None:raise RuntimeError('Inspection camera must not have an animation track')
                path=out/(label+'.png');scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
                evaluated=inspection.evaluated_get(bpy.context.evaluated_depsgraph_get())
                if (evaluated.matrix_world.translation-position).length>1e-5:raise RuntimeError('Inspection camera pose was overridden')
                report['detail_views'].append({'name':label,'frame_time_s':0,'position':list(position),'target':list(target),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        report.update(completed=True,engine=engine,blend_path=str(out/'district.blend'),samples_requested=a.samples,
            width=scene.render.resolution_x*a.resolution_percent//100,height=scene.render.resolution_y*a.resolution_percent//100,
            native_blender_executed=True,render_device='CPU' if engine=='CYCLES' else 'EEVEE OpenGL',
            exposure=scene.view_settings.exposure,sky_strength=world.node_tree.nodes['Background'].inputs[1].default_value)
    finally:
        report['elapsed_s']=time.monotonic()-t0
        (out/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
