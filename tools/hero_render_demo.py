"""Native path-traced art review plus normalized asset exports. No Jev or physics."""
import argparse,json,sys,math,time,shutil
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from hero_asset_kit import build_kit,box,pbr,collection,sha

def camera_at(scene,position,target,lens=35):
    camera=scene.camera;camera.location=position;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=lens

def instance(scene,col,name,location,yaw=0):
    obj=bpy.data.objects.new(name,None);obj.instance_type='COLLECTION';obj.instance_collection=col
    scene.collection.objects.link(obj);obj.location=location;obj.rotation_euler.z=yaw
    return obj

def photographic_material(root,ident,name):
    mat=pbr(name,(.4,.4,.4),.55);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    shader=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    coords=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=.5;links.new(coords.outputs['Object'],mapping.inputs[0])
    for role,socket in [('Diffuse','Base Color'),('Rough','Roughness')]:
        node=nodes.new('ShaderNodeTexImage');node.image=bpy.data.images.load(str(root/ident/(role+'.jpg')));node.projection='BOX';node.projection_blend=.2
        node.image.colorspace_settings.name='sRGB' if role=='Diffuse' else 'Non-Color'
        links.new(mapping.outputs[0],node.inputs['Vector']);links.new(node.outputs['Color'],shader.inputs[socket])
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=220
    links.new(coords.outputs['Object'],noise.inputs['Vector']);bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.002
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal'])
    return mat

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);root=args.assets.resolve();out=args.out.resolve()
    if out.exists():raise FileExistsError('New output folder required')
    if not bpy.app.background:raise RuntimeError('Background only')
    out.mkdir(parents=True);started=time.perf_counter();bpy.ops.wm.read_factory_settings(use_empty=True)
    kit=build_kit(root);source_ids={k:[o.name for o in col.objects] for k,(col,_) in kit.items()}
    bpy.ops.file.pack_all();assets=out/'models';assets.mkdir()
    inventory={}
    original_scene=bpy.context.scene
    for key,(col,meta) in kit.items():
        temp=bpy.data.scenes.new('Export_'+key);temp.collection.children.link(col);bpy.context.window.scene=temp;temp.frame_set(1)
        path=assets/(key+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_animations=False,export_apply=True)
        tris=0
        for o in col.objects:
            if o.type=='MESH':o.data.calc_loop_triangles();tris+=len(o.data.loop_triangles)
        inventory[key]={**meta,'bytes':path.stat().st_size,'sha256':sha(path),'triangles_before_export_modifiers':tris,'export_axes':'glTF Y-up; metres'}
        bpy.context.window.scene=original_scene;bpy.data.scenes.remove(temp)
    bpy.data.libraries.write(str(assets/'hero-library.blend'),set(v[0] for v in kit.values()),fake_user=True,compress=True)
    s=bpy.context.scene;architecture=collection('AuthoredStreetArchitecture');s.collection.children.link(architecture)
    granite=photographic_material(root,'granite_tile_02','Photographic granite, authored placement')
    marble=photographic_material(root,'marble_01','Photographic marble, authored placement')
    metal=pbr('Architectural bronze',(.11,.095,.065),.32,.75);black=pbr('Window frames',(.018,.022,.024),.38,.6)
    glass=pbr('Facade glazing',(.77,.85,.89),.055,transmission=1)
    asphalt=pbr('Fine asphalt',(.095,.105,.11),.83);light=pbr('Warm lobby light',(1,.74,.42),.35,emission=3)
    box(architecture,'Road',(0,15,-.12),(8,90,.22),asphalt)
    for side in [-1,1]:
        box(architecture,'Sidewalk',(side*6,15,-.025),(4,90,.35),granite)
        for y in range(-28,60,2):box(architecture,'Bevelled curb',(side*4.05,y,.085),(.22,1.97,.24),marble,.025)
        for block,y in enumerate([0,16,32,48]):
            x=side*10.8
            box(architecture,'Authored building volume',(x,y,14),(4.4,15.5,28),granite)
            box(architecture,'Lobby floor',(side*9.0,y,.22),(2.4,15,.20),marble)
            box(architecture,'Lobby dark depth',(side*10.4,y,2.2),(.08,14.5,4.0),black,.003)
            for yy in [y-6,y-3,y,y+3,y+6]:
                box(architecture,'Stone pilaster',(side*8.1,yy,2.8),(.28,.22,5.3),granite)
                box(architecture,'Glazed shop bay',(side*8.15,yy+1.4,2.65),(.035,2.5,4.7),glass,.004)
                box(architecture,'Horizontal transom',(side*8.0,yy+1.4,4.7),(.10,2.5,.075),black,.004)
                box(architecture,'Interior shelf',(side*9.6,yy+1.4,1.0),(.45,1.2,.9),marble)
                box(architecture,'Lobby light',(side*9.0,yy+1.4,4.85),(1.1,.045,.035),light,.003)
            box(architecture,'Canopy',(side*7.5,y,5.35),(1.9,14.5,.16),metal)
        for y in [-4,11,26,41]:instance(s,kit['tree'][0],'Authored street tree',(side*5.2,y,.15),y*.13)
        for y in [5,31,51]:
            instance(s,kit['bench'][0],'Assembled street bench',(side*6.8,y,.15),side*math.pi/2)
            instance(s,kit['planter'][0],'Fern planter',(side*6.8,y+2.9,.15),math.pi/2)
    lead=instance(s,kit['car'][0],'Hero lead coupe',(0,4,0))
    world=bpy.data.worlds.new('Authored daylight');world.use_nodes=True;world.node_tree.nodes.clear()
    background=world.node_tree.nodes.new('ShaderNodeBackground');background.inputs['Strength'].default_value=.32
    sky=world.node_tree.nodes.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_elevation=math.radians(45);sky.sun_rotation=math.radians(130)
    world.node_tree.links.new(sky.outputs[0],background.inputs[0]);output=world.node_tree.nodes.new('ShaderNodeOutputWorld');world.node_tree.links.new(background.outputs[0],output.inputs[0]);s.world=world
    sun_data=bpy.data.lights.new('Authored key','SUN');sun_data.energy=1.4;sun_data.angle=.06
    sun=bpy.data.objects.new('Authored key',sun_data);s.collection.objects.link(sun);sun.rotation_euler=(.35,-.4,-.6)
    cam_data=bpy.data.cameras.new('ReviewCamera');cam=bpy.data.objects.new('ReviewCamera',cam_data);s.collection.objects.link(cam);s.camera=cam;cam_data.clip_end=500
    s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=48;s.cycles.use_denoising=True;s.cycles.max_bounces=6;s.cycles.transparent_max_bounces=8
    s.render.resolution_x=1920;s.render.resolution_y=1080;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
    s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=0
    report={'schema':'jevdrive.hero-native-review.v1','blender':bpy.app.version_string,'engine':'CYCLES','device':'CPU','samples':48,'assets':inventory,'source_lock_sha256':sha(root/'download-lock.json'),'script_sha256':sha(__file__),'kit_script_sha256':sha(Path(__file__).with_name('hero_asset_kit.py')),'images':[],'jev_calls':0,'physics_simulated':False,'photorealism_verified':False,'scene_geography':'Authored art-review street, NOT a reconstruction of Marunouchi','native_vegetation_count':8,'native_bench_count':6,'native_planter_count':6,'cars':1}
    shots=[('street-ego',(-1,-10,1.55),(0,14,1.7),25),('car-detail',(5,10,2.8),(0,4,.85),48),('bench-detail',(-2.9,2,1.8),(-6.8,5,.8),48)]
    for name,position,target,lens in shots:
        camera_at(s,position,target,lens);path=out/(name+'.png');s.render.filepath=str(path)
        before=time.perf_counter();bpy.ops.render.render(write_still=True)
        report['images'].append({'name':path.name,'sha256':sha(path),'width':1920,'height':1080,'seconds':time.perf_counter()-before})
        (out/'review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    camera_at(s,shots[0][1],shots[0][2],shots[0][3]);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'hero-street.blend'))
    shutil.copy2(root/'SOURCES.txt',out/'SOURCES.txt');shutil.copy2(root/'download-lock.json',out/'download-lock.json');shutil.copy2(root/'extracted-lock.json',out/'extracted-lock.json')
    report['total_seconds']=time.perf_counter()-started;report['completed']=True
    (out/'review.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps({'complete':True,'out':str(out),'seconds':report['total_seconds']}))

if __name__=='__main__':main()
