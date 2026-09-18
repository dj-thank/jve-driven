"""Reusable source-attributed art assets. Run inside Blender, with autoexec disabled."""
from pathlib import Path
import math,hashlib,json,sys
import bpy
import numpy as np
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from jevdrive.hero_assets import normalize_car_bounds,verify_asset_lock,file_sha256

sha=file_sha256

def bounds(objects):
    lows=[];highs=[]
    for o in objects:
        if o.type!='MESH':continue
        raw=np.empty(len(o.data.vertices)*3,np.float32);o.data.vertices.foreach_get('co',raw)
        matrix=np.asarray(o.matrix_world,float);pts=raw.reshape(-1,3)@matrix[:3,:3].T+matrix[:3,3]
        if not len(pts) or not np.isfinite(pts).all():raise ValueError('Invalid source geometry')
        lows.append(pts.min(0));highs.append(pts.max(0))
    if not lows:raise ValueError('No mesh bounds')
    return Vector(np.min(lows,axis=0)),Vector(np.max(highs,axis=0))

def collection(name):return bpy.data.collections.new('Hero_'+name)

def adopt(obj,col):
    for c in list(obj.users_collection):c.objects.unlink(obj)
    col.objects.link(obj)

def append_objects(path,names,col):
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):
        if not set(names)<=set(src.objects):raise ValueError('Asset object names changed')
        dst.objects=names
    for obj in dst.objects:col.objects.link(obj);obj.animation_data_clear()
    return list(dst.objects)

def pbr(name,color,rough=.5,metal=0,transmission=0,coat=0,emission=0):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.node_tree.nodes.clear()
    p=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled');out=m.node_tree.nodes.new('ShaderNodeOutputMaterial');m.node_tree.links.new(p.outputs['BSDF'],out.inputs['Surface'])
    for key,value in [('Base Color',(*color,1)),('Roughness',rough),('Metallic',metal),('Transmission Weight',transmission),('Coat Weight',coat),('IOR',1.46)]:
        if key in p.inputs:p.inputs[key].default_value=value
    if emission:
        p.inputs['Emission Color'].default_value=(*color,1);p.inputs['Emission Strength'].default_value=emission
    return m

def bake(o,transform=None):
    matrix=Matrix.Identity(4) if transform is None else transform
    o.data=o.data.copy();o.data.transform(matrix@o.matrix_world);o.parent=None;o.matrix_world=Matrix.Identity(4)
    for mod in list(o.modifiers):o.modifiers.remove(mod)
    o.data.update()

def box(col,name,location,size,mat,bevel=.015):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);o=bpy.context.object;o.name=name;o.scale=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat);adopt(o,col)
    if bevel:
        mod=o.modifiers.new('Edge radius','BEVEL');mod.width=bevel;mod.segments=3
    return o

def car_asset(root):
    before=set(bpy.data.objects);bpy.ops.wm.obj_import(filepath=str(root/'bmw/bmw.obj'))
    objects=[o for o in bpy.data.objects if o not in before and o.type=='MESH'];col=collection('TouringCoupe')
    lo,hi=bounds(objects);transform=Matrix(normalize_car_bounds(lo,hi).tolist())
    materials={
        'paint':pbr('Hero_PearlGraphite',(.065,.095,.12),.21,.62,coat=.85),
        'glass':pbr('Hero_Glass',(.70,.79,.84),.06,0,transmission=1),
        'chrome':pbr('Hero_Aluminium',(.62,.65,.68),.23,.95),
        'rubber':pbr('Hero_Rubber',(.012,.013,.015),.87),
        'dark':pbr('Hero_Trim',(.022,.025,.028),.5),
        'inside':pbr('Hero_Interior',(.12,.065,.038),.63),
        'brake':pbr('Hero_BrakeMetal',(.18,.19,.20),.5,.85),
        'tail':pbr('Hero_TailLens',(.32,.004,.009),.2,coat=.6,emission=.8),
        'light':pbr('Hero_HeadLens',(.8,.86,.93),.13,coat=.8,emission=1.2)}
    kept=[];removed=[]
    for o in objects:
        if 'roundel' in o.name.lower():removed.append(o.name);bpy.data.objects.remove(o,do_unlink=True);continue
        original=[m.name if m else '' for m in o.data.materials]
        bake(o,transform);adopt(o,col)
        for i,name in enumerate(original):
            n=name.lower();key='dark'
            if 'carshellnew' in n:key='paint'
            elif n=='glass' or 'window' in n:key='glass'
            elif 'rubber' in n:key='rubber'
            elif 'chrome' in n or 'silver' in n or n=='mirror':key='chrome'
            elif 'interior' in n:key='inside'
            elif 'tail' in n:key='tail'
            elif 'light' in n and 'matte' not in n:key='light'
            elif 'brake' in n:key='brake'
            o.data.materials[i]=materials[key]
        kept.append(o)
    tires=[o for o in kept if 'TireRubber' in o.name];pivots=[]
    if len(tires)!=4:raise ValueError('Expected four separately identifiable tires')
    for i,o in enumerate(tires):
        a,b=bounds([o]);center=(a+b)/2;p=bpy.data.objects.new('Hero_WheelPivot_'+str(i),None);col.objects.link(p)
        p.location=center;p['radius_m']=(b.z-a.z)/2;pivots.append(p)
    for o in kept:
        if o.name.startswith('Tire'):
            a,b=bounds([o]);p=min(pivots,key=lambda q:((a+b)/2-q.location).length)
            o.data.transform(Matrix.Translation(-p.location));o.parent=p;o.matrix_parent_inverse=Matrix.Identity(4);o.data.update()
    return col,{'source':'Mike Pan / Morgan McGuire BMW','license':'CC0-1.0','length_m':4.75,'forward':'+Y','up':'+Z','removed_brand_meshes':removed,'wheel_pivots':len(pivots),'materials_authored':True,'vehicle_class':'coupe, not a measured sedan'}

def tree_asset(root):
    col=collection('StreetTree_LOD1');o=append_objects(next((root/'tree_small_02').glob('*.blend')),['tree_small_02_LOD1'],col)[0]
    lo,hi=bounds([o]);bake(o,Matrix.Scale(6.5/(hi.z-lo.z),4)@Matrix.Translation(Vector((0,0,-lo.z))))
    return col,{'source':'Poly Haven tree_small_02','license':'CC0-1.0','selected_source_lod':1,'height_m':6.5,'species_and_dimensions_authored':True}

def bench_asset(root):
    col=collection('StreetBench');seat,back,leg,arm=append_objects(next((root/'modular_street_seating').glob('*.blend')),['seat_bench','seat_back','legs_single','arm_rest_01'],col)
    for o in [seat,back,leg,arm]:bake(o)
    seat.location=(0,0,.475);lo,hi=bounds([back]);back.data.transform(Matrix.Rotation(math.radians(80),4,'X')@Matrix.Translation(-(lo+hi)/2));back.location=(0,.27,.70)
    leg.location.x=-.68;leg2=leg.copy();col.objects.link(leg2);leg2.location.x=.68
    arm.location=(-.85,0,.475);arm2=arm.copy();col.objects.link(arm2);arm2.location=(.85,0,.475)
    steel=pbr('Hero_BenchSupport',(.10,.12,.12),.34,.8)
    for x in [-.72,.72]:box(col,'Back support',(x,.275,.59),(.025,.035,.55),steel,.005)
    return col,{'source':'Poly Haven modular_street_seating','license':'CC0-1.0','assembly':'seat/back/two legs/two armrests; authored support struts','seat_height_m':.475}

def planter_asset(root):
    col=collection('FernPlanter');mat=pbr('Hero_PlanterMetal',(.034,.043,.04),.39,.55);soil=pbr('Hero_Soil',(.035,.023,.012),.97)
    box(col,'Planter base',(0,0,.12),(1.4,.64,.20),mat)
    for x in [-.68,.68]:box(col,'Planter wall',(x,0,.46),(.055,.64,.67),mat)
    for y in [-.30,.30]:box(col,'Planter wall',(0,y,.46),(1.4,.055,.67),mat)
    box(col,'Soil',(0,0,.64),(1.29,.52,.08),soil,.005)
    plants=append_objects(next((root/'fern_02').glob('*.blend')),['fern_02_a','fern_02_b','fern_02_c','fern_02_d'],col)
    for i,o in enumerate(plants):
        lo,hi=bounds([o]);bake(o,Matrix.Scale(1.5,4)@Matrix.Translation(Vector((0,0,-lo.z))))
        o.location=(-.43+i*.28,(-1)**i*.1,.69);o.rotation_euler.z=i*1.65
    return col,{'source':'Poly Haven fern_02 + authored planter','license':'CC0-1.0','placement_and_species_authored':True}

def build_kit(root):
    root=Path(root).resolve();verify_asset_lock(root)
    extracted=json.loads((root/'extracted-lock.json').read_text(encoding='utf8'))
    if sha(root/'bmw/bmw.zip')!=extracted['archive_sha256']:raise ValueError('Wrong car archive')
    for row in extracted['resources']:
        p=(root/row['path']).resolve()
        if not p.is_relative_to(root) or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('Extracted car source changed')
    return {key:fn(root) for key,fn in [('car',car_asset),('tree',tree_asset),('bench',bench_asset),('planter',planter_asset)]}
