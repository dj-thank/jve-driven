"""Native Cycles review and asset exports. Authored street, not measured Tokyo.

Optional full-district integration is intentionally not claimed by this review.
All people poses and all placements are authored; no Jev or vehicle physics.
"""
from __future__ import annotations
import argparse,json,math,time,shutil,os
from pathlib import Path
import bpy
from mathutils import Vector
from native_assets import prepare,new_material,bounds
from validation import sha,assert_font_free


def box(col,name,loc,scale,mat,bevel=.01):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    for c in list(o.users_collection):c.objects.unlink(o)
    col.objects.link(o);o.data.materials.append(mat)
    if bevel:
        m=o.modifiers.new('Physical edge radius','BEVEL');m.width=bevel;m.segments=2
    return o


def cylinder(col,name,loc,radius,depth,mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=radius,depth=depth,location=loc)
    o=bpy.context.object;o.name=name
    for c in list(o.users_collection):c.objects.unlink(o)
    col.objects.link(o);o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    return o


def linked_instance(scene,col,name,xyz,yaw=0):
    o=bpy.data.objects.new(name,None);o.instance_type='COLLECTION';o.instance_collection=col
    scene.collection.objects.link(o);o.location=xyz;o.rotation_euler.z=yaw
    return o


def photographed(root,ident,name,scale=.5):
    m,p=new_material(name,(.4,.4,.4),.65);n=m.node_tree.nodes;l=m.node_tree.links
    coord=n.new('ShaderNodeTexCoord');anchor=bpy.data.objects.get('MaterialMetres')
    if anchor is None:
        anchor=bpy.data.objects.new('MaterialMetres',None);bpy.context.scene.collection.objects.link(anchor)
    coord.object=anchor;mapping=n.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=scale
    l.new(coord.outputs['Object'],mapping.inputs[0])
    for role,target in [('Diffuse','Base Color'),('Rough','Roughness'),('nor_gl',None)]:
        img=n.new('ShaderNodeTexImage');img.image=bpy.data.images.load(str((root/ident/(role+'.jpg')).resolve()),check_existing=True)
        img.image.colorspace_settings.name='sRGB' if role=='Diffuse' else 'Non-Color';img.image.pack()
        img.projection='BOX';img.projection_blend=.1;l.new(mapping.outputs[0],img.inputs['Vector'])
        if target:l.new(img.outputs['Color'],p.inputs[target])
        else:
            normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.35
            l.new(img.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],p.inputs['Normal'])
    return m


def lettering(col,text,loc,rotation,size,mat):
    curve=bpy.data.curves.new('Authored sign','FONT');curve.body=text;curve.size=size;curve.align_x='CENTER';curve.extrude=.003
    obj=bpy.data.objects.new('Fictional sign '+text,curve);col.objects.link(obj);obj.location=loc;obj.rotation_euler=rotation;obj.data.materials.append(mat)
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.ops.object.convert(target='MESH')


def scene_geometry(scene,assets,kit):
    arch=bpy.data.collections.new('AuthoredArchitecture');scene.collection.children.link(arch)
    stone,_=new_material('Warm limestone',(.42,.39,.33),.66)
    stone2,_=new_material('Cool light granite',(.37,.39,.38),.72)
    bronze,_=new_material('Brushed bronze',(.20,.14,.075),.3,.8)
    black,_=new_material('Dark window framing',(.025,.03,.035),.34,.55)
    glass,_=new_material('Architectural glazing',(.85,.91,.92),.065,0,.98)
    concrete,_=new_material('Concrete',(.27,.27,.25),.83)
    timber,_=new_material('Lobby walnut',(.09,.045,.023),.58)
    white,_=new_material('Road paint',(.65,.65,.59),.75)
    warm,shader=new_material('Warm LED',(1,.68,.35),.45);shader.inputs['Emission Color'].default_value=(1,.6,.28,1);shader.inputs['Emission Strength'].default_value=2
    road=photographed(assets,'pavement_01','Photographic stone roadway',.48)
    sidewalk=photographed(assets,'pavement_05','Photographic sidewalk',.42)
    box(arch,'Wide authored base',(0,0,-.25),(640,400,.45),concrete,0)
    box(arch,'Stone carriageway',(0,0,-.055),(8.2,390,.11),road,0)
    for side in (-1,1):
        box(arch,'Broad sidewalk',(side*6.65,0,.06),(5.1,390,.18),sidewalk,.008)
        for y in range(-180,181,2):
            if 50<y<62:continue
            box(arch,'Curb',(side*4.15,y,.075),(.22,1.98,.15),stone2,.018)
        for i,y in enumerate(range(-24,133,18)):
            h=28+(i%4)*10;mat=stone if i%2 else stone2
            box(arch,'Upper building mass',(side*14.8,y,5+h/2),(10.4,17.5,h),mat,.035)
            box(arch,'Lobby floor',(side*12.15,y,.205),(5.1,17.3,.11),stone2,.005)
            box(arch,'Lobby ceiling',(side*12.15,y,4.9),(5.1,17.3,.15),mat,.005)
            box(arch,'Recessed lobby back',(side*14.5,y,2.55),(.12,16.8,4.65),timber,.01)
            for dy in (-7,-3.5,0,3.5,7):
                yy=y+dy
                box(arch,'Limestone pier',(side*9.65,yy,2.6),(.48,.30,4.9),mat,.018)
                if dy<7:
                    middle=yy+1.73
                    box(arch,'Shop glazing',(side*9.58,middle,2.52),(.025,3.12,4.5),glass,.003)
                    box(arch,'Door mullion',(side*9.51,middle,2.52),(.075,.058,4.6),black,.004)
                    for z in (.34,3.25,4.78):box(arch,'Window transom',(side*9.51,middle,z),(.07,3.15,.065),black,.004)
                    box(arch,'Brass door handle',(side*9.43,middle+.13,1.1),(.045,.025,.38),bronze,.009)
                    box(arch,'Display cabinet',(side*12.8,middle,.79),(1.1,1.8,1.15),timber,.025)
                    box(arch,'Display light',(side*11.8,middle,4.70),(1.25,.045,.035),warm,.003)
            box(arch,'Bronze canopy',(side*9.12,y,4.95),(1.6,16.8,.13),bronze,.014)
            # Multiple actual recessed window bays, not an upscaled facade photograph.
            for level in range(7,int(h)+3,4):
                for dy in (-6.8,-3.4,0,3.4,6.8):
                    box(arch,'Upper dark reveal',(side*9.535,y+dy,level),(.045,2.88,2.65),black,.006)
                    box(arch,'Upper reflecting glass',(side*9.50,y+dy,level),(.024,2.55,2.34),glass,.002)
            lettering(arch,['AOI ATELIER','NAMI COFFEE','KIRI GALLERY'][i%3],(side*9.42,y,4.15),(math.pi/2,0,side*math.pi/2),.25,bronze)
        for y in (-12,12,36,78,102,126):
            cylinder(arch,'Street light',(side*5.65,y,2.75),.07,5.3,black)
            box(arch,'Street light head',(side*5.35,y,5.40),(.85,.26,.11),black,.04)
        for x,y in ((35,-12),(58,12),(82,48),(36,87),(63,130),(110,-45)):
            box(arch,'Authored background volume',(side*x,y,22+(x%3)*8),(22,32,44+(x%3)*16),stone2,.03)
    for y in range(-30,151,8):
        if 47<y<65:continue
        box(arch,'Lane marking',(0,y,.009),(.11,3.0,.008),white,0)
    for x in (-3.6,-2.4,-1.2,0,1.2,2.4,3.6):box(arch,'Crosswalk',(x,48,.012),(.65,4,.012),white,0)
    box(arch,'Stop line',(-2,44.9,.012),(3.7,.35,.012),white,0)
    placed=[]
    for side in (-1,1):
        for y in (0,20,40,76,96,116):placed.append(linked_instance(scene,kit['tree'][0],'External street tree',(side*5.7,y,.15),y*.37))
        for y in (8,31,84,107):
            placed.append(linked_instance(scene,kit['bench'][0],'External assembled bench',(side*7.4,y,.15),side*math.pi/2))
            placed.append(linked_instance(scene,kit['plant'][0],'External potted plant',(side*8.8,y+2,.15)))
    placed.append(linked_instance(scene,kit['car'][0],'External lead coupe',(-1.9,7,0)))
    placed.append(linked_instance(scene,kit['car'][0],'External parked coupe',(1.8,82,0)))
    for i,(x,y) in enumerate([(-7.6,3),(7.3,13),(-8,29),(8,37),(-7.5,66),(7.8,92),(-8,110),(7.3,115)]):
        placed.append(linked_instance(scene,kit['male' if i%2==0 else 'female'][0],'Textured business pedestrian',(x,y,.15),(i%3-1)*.7))
    return arch,placed


def cam(scene,pos,target,fov=78):
    scene.camera.location=pos;scene.camera.rotation_euler=(Vector(target)-Vector(pos)).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.sensor_fit='HORIZONTAL';scene.camera.data.sensor_width=36
    scene.camera.data.lens=18/math.tan(math.radians(fov/2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--people',type=Path,required=True);p.add_argument('--legacy-library',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--samples',type=int,default=16);p.add_argument('--width',type=int,default=1280)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError('A new output directory is required')
    a.out.mkdir(parents=True);out=a.out.resolve();started=time.perf_counter()
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kit,rigs,evidence=prepare(a.assets,a.people,a.legacy_library)
    for m in list(bpy.data.materials):
        if m.users==0:bpy.data.materials.remove(m)
    for image in list(bpy.data.images):
        if image.users==0:bpy.data.images.remove(image)
    scene=bpy.context.scene;inventory={};(out/'models').mkdir()
    # Standalone six-asset library, exported before costly images so completion is independent.
    for key,(col,meta) in kit.items():
        temp=bpy.data.scenes.new('Export_'+key);temp.collection.children.link(col);bpy.context.window.scene=temp
        path=out/'models'/(key+'.glb');bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_animations=False,export_apply=True)
        inventory[key]={**meta,'output_sha256':sha(path),'output_bytes':path.stat().st_size}
        bpy.context.window.scene=scene;bpy.data.scenes.remove(temp)
    bpy.ops.file.pack_all()
    bpy.data.libraries.write(str(out/'models/asset-library.blend'),set([v[0] for v in kit.values()]+rigs),fake_user=True,compress=True)
    report={'schema':'asset-studio.native-review.v1','completed':False,'asset_export_completed':True,'blender':bpy.app.version_string,'engine':'CYCLES','device':'CPU','source_evidence':evidence,'assets':inventory,'images':[],
        'scene_mode':'authored Marunouchi-inspired asset-review street, not an exact Tokyo reconstruction',
        'base_area_m':[640,400],'ground_floor_buildings':18,'hero_street_length_m':180,
        'placement_counts':{'trees':12,'benches':8,'plants':8,'cars':2,'people':8},
        'source_v06_district_modified':False,'used_existing_v06_district_file':False,
        'jev_calls':0,'physics_simulated':False,'photorealism_verified':False,'paid_purchases':0,
        'pose_and_roughness_authored':True,'people_are_static_poses':True,'font_files_distributed':0,'code_sha256':sha(__file__)}
    def save(): (out/'review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    save();arch,instances=scene_geometry(scene,a.assets.resolve(),kit)
    camera_data=bpy.data.cameras.new('CarHeightReview');camera=bpy.data.objects.new('CarHeightReview',camera_data);scene.collection.objects.link(camera);scene.camera=camera;camera_data.clip_start=.05;camera_data.clip_end=700
    world=bpy.data.worlds.new('Photographic HDRI');world.use_nodes=True;nodes=world.node_tree.nodes;nodes.clear()
    image=nodes.new('ShaderNodeTexEnvironment');image.image=bpy.data.images.load(str((a.assets/'sky/sky.hdr').resolve()));image.image.pack()
    bg=nodes.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.7;output=nodes.new('ShaderNodeOutputWorld')
    world.node_tree.links.new(image.outputs['Color'],bg.inputs['Color']);world.node_tree.links.new(bg.outputs[0],output.inputs[0]);scene.world=world
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=a.samples;scene.cycles.use_denoising=True;scene.cycles.max_bounces=5;scene.cycles.transmission_bounces=4;scene.cycles.transparent_max_bounces=8
    scene.render.threads_mode='FIXED';scene.render.threads=4
    scene.render.resolution_x=a.width;scene.render.resolution_y=round(a.width*9/16);scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=0
    shots=[('street-ego',(-1.9,-10,1.55),(-1.9,32,1.7),78),('car-detail',(3.5,13,2.1),(-1.9,7,.82),46),('sidewalk-detail',(-3.1,-.8,1.55),(-7.5,6,1.2),50)]
    for name,pos,target,fov in shots:
        cam(scene,pos,target,fov);scene.render.filepath=str(out/(name+'.png'));t=time.perf_counter();bpy.ops.render.render(write_still=True)
        path=out/(name+'.png');report['images'].append({'name':path.name,'sha256':sha(path),'width':scene.render.resolution_x,'height':scene.render.resolution_y,'camera':list(pos),'target':list(target),'horizontal_fov':fov,'samples':a.samples,'seconds':time.perf_counter()-t});save()
    cam(scene,*shots[0][1:]);bpy.ops.file.pack_all()
    for curve in list(bpy.data.curves):
        if curve.users==0:bpy.data.curves.remove(curve)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'asset-street.blend'))
    shutil.copy2(a.people/'LICENSE-Microsoft-Rocketbox.md',out/'LICENSE-Microsoft-Rocketbox.md')
    (out/'SOURCES.txt').write_text('Authored asset-review street, not real Tokyo. No Jev, no vehicle physics.\nCar: Mike Pan / Morgan McGuire, CC0 / Public Domain. Reused prepared car and tree from repository commit 46ad223ff7d8ae0ccbb6e2913d37ebfb2ba0526d.\nTrees, seating, potted plant, pavement and HDRI: Poly Haven, CC0-1.0. Powered by Poly Haven.\nHumans: Microsoft Rocketbox, MIT, Copyright (c) 2020 Microsoft; license included.\nhttps://casual-effects.com/g3d/data10/\nhttps://polyhaven.com/license\nhttps://github.com/microsoft/Microsoft-Rocketbox\nAll placements, relaxed poses and material tuning are authored. No endorsement is implied.\n',encoding='utf8')
    assert_font_free(out);report.update(completed=True,total_seconds=time.perf_counter()-started,scene_sha256=sha(out/'asset-street.blend'));save();print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
