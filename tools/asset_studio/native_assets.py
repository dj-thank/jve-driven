"""Actual Blender asset preparation. Imported data and authored changes stay distinct."""
from __future__ import annotations
import json,math
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
from validation import sha,verify_downloads,assert_dimensions


def bounds(objects,evaluated=False):
    points=[];dg=bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type!='MESH':continue
        obj=obj.evaluated_get(dg) if evaluated else obj
        points.extend(obj.matrix_world@Vector(corner) for corner in obj.bound_box)
    if not points:raise ValueError('No mesh in asset')
    return Vector([min(p[i] for p in points) for i in range(3)]),Vector([max(p[i] for p in points) for i in range(3)])


def move_to_collection(objects,name):
    col=bpy.data.collections.new(name)
    for obj in objects:
        for old in list(obj.users_collection):old.objects.unlink(obj)
        col.objects.link(obj)
    return col


def import_gltf(path):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
    return [o for o in bpy.data.objects if o not in before]


def ground_objects(objects):
    bpy.context.view_layer.update();lo,hi=bounds(objects)
    delta=Vector((0,0,-lo.z))
    # Apply only to hierarchy roots, preserving wheel children and imported transforms.
    selected=set(objects)
    for obj in objects:
        if obj.parent not in selected:obj.matrix_world=Matrix.Translation(delta)@obj.matrix_world
    bpy.context.view_layer.update()


def texture(root,name,noncolor=False):
    file=Path(root)/name
    if not file.is_file():raise ValueError('Required source image is missing: '+name)
    image=bpy.data.images.load(str(file.resolve()),check_existing=True)
    image.colorspace_settings.name='Non-Color' if noncolor else 'sRGB'
    image.pack()
    return image


def new_material(name,color,rough=.5,metal=0,transmission=0):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    p=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough
    p.inputs['Metallic'].default_value=metal;p.inputs['Transmission Weight'].default_value=transmission
    return mat,p


def business_avatar(root,name,prefix):
    root=Path(root)/name;before=set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str((root/'Export'/(name+'.fbx')).resolve()),use_image_search=False)
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH'];arms=[o for o in imported if o.type=='ARMATURE']
    if len(meshes)!=1 or len(arms)!=1:raise ValueError('Unexpected avatar mesh/rig inventory')
    rig=arms[0]
    for obj in imported:obj.animation_data_clear()
    # FBX contains stale original-author paths. Rebuild against our hash-checked local maps.
    materials={}
    for part in ('body','head','opacity'):
        mat,p=new_material(name+'_'+part,(.3,.3,.3),.68 if part=='body' else .5)
        n=mat.node_tree.nodes;links=mat.node_tree.links
        image=n.new('ShaderNodeTexImage');image.image=texture(root/'Textures',prefix+'_'+part+'_color.tga')
        links.new(image.outputs['Color'],p.inputs['Base Color'])
        if part=='opacity':
            links.new(image.outputs['Alpha'],p.inputs['Alpha']);mat.surface_render_method='DITHERED'
        else:
            normal=n.new('ShaderNodeTexImage');normal.image=texture(root/'Textures',prefix+'_'+part+'_normal.tga',True)
            convert=n.new('ShaderNodeNormalMap');convert.inputs['Strength'].default_value=.4
            links.new(normal.outputs['Color'],convert.inputs['Color']);links.new(convert.outputs['Normal'],p.inputs['Normal'])
        materials[part]=mat
    for obj in meshes:
        for i,old in enumerate(obj.data.materials):
            part=next((part for part in materials if old.name.endswith(part)),None)
            if part is None:raise ValueError('Unrecognized avatar material '+old.name)
            obj.data.materials[i]=materials[part]
    bpy.context.view_layer.update()
    changes=[]
    # Authored relaxed standing pose. This is NOT a retargeted walking animation.
    for side,sign in [('L',1),('R',-1)]:
        bone=rig.pose.bones['Bip01 '+side+' UpperArm']
        elbow=rig.pose.bones['Bip01 '+side+' Forearm']
        direction=(elbow.head-bone.head).normalized()
        target=Vector((.02,sign*.18,-1)).normalized()
        rotation=direction.rotation_difference(target).to_matrix()
        pose=bone.matrix.copy();orientation=rotation@pose.to_3x3()
        bone.matrix=Matrix.Translation(pose.translation)@orientation.to_4x4()
        bpy.context.view_layer.update();changes.append({'bone':bone.name,'arm_direction_armature_space':list(target)})
    source_col=move_to_collection(imported,'Rigged_'+name)
    # Temporarily link for evaluated skinning; do not mutate the source FBX or flatten its rig.
    bpy.context.scene.collection.children.link(source_col)
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();posed=[]
    for obj in meshes:
        evaluated=obj.evaluated_get(dg)
        mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=dg)
        mesh.transform(Matrix.Rotation(math.pi,4,'Z')@obj.matrix_world)
        baked=bpy.data.objects.new('Posed_'+name,mesh);bpy.context.scene.collection.objects.link(baked);posed.append(baked)
    ground_objects(posed);lo,hi=bounds(posed);extent=assert_dimensions(list(lo),list(hi),'person')
    bpy.context.scene.collection.children.unlink(source_col)
    col=move_to_collection(posed,'Studio_'+name)
    return col,source_col,{'source':'Microsoft Rocketbox '+name,'license':'MIT','copyright':'Copyright (c) 2020 Microsoft',
        'source_fbx_sha256':sha(root/'Export'/(name+'.fbx')),'triangles':sum(len(o.data.polygons) for o in posed),
        'bounds_z_up_m':[list(lo),list(hi)],'dimensions_m':extent,'rig_bones':len(rig.data.bones),
        'texture_paths_repaired':True,'authored_roughness':True,'normal_strength':.4,
        'pose_changes':changes,'motion_capture_used':False,'walk_animation_complete':False}


def reviewed_bench(root):
    objects=import_gltf(Path(root)/'modular_street_seating/modular_street_seating.gltf')
    wanted={'crossbar','legs_single','legs_double','back_support_l','back_support_r','arm_rest_01','seat','seat_back'}
    chosen=[]
    for obj in objects:
        if obj.name not in wanted:bpy.data.objects.remove(obj,do_unlink=True);continue
        obj.location.x+=1.16;chosen.append(obj)
    if len(chosen)!=8:raise ValueError('Source bench component names changed')
    arm=next(o for o in chosen if o.name=='arm_rest_01');other=arm.copy();other.data=arm.data
    bpy.context.scene.collection.objects.link(other);other.location.x+=2.32;chosen.append(other)
    ground_objects(chosen);lo,hi=bounds(chosen);extent=assert_dimensions(list(lo),list(hi),'bench')
    col=move_to_collection(chosen,'Studio_Bench')
    return col,{'source':'Poly Haven modular_street_seating','license':'CC0-1.0','components':len(chosen),
        'assembly':'Native relative arrangement retained; right armrest duplicated; unused variants removed',
        'bounds_z_up_m':[list(lo),list(hi)],'dimensions_m':extent,'seat_height_m':.45}


def reviewed_plant(root):
    objects=import_gltf(Path(root)/'potted_plant_02/potted_plant_02.gltf')
    reductions=[]
    for obj in objects:
        if obj.type=='MESH' and 'dirt' in obj.name:
            before=len(obj.data.polygons);mod=obj.modifiers.new('Reduce hidden soil tessellation','DECIMATE');mod.ratio=.08
            bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=mod.name)
            reductions.append({'name':obj.name,'polygons_before':before,'polygons_after':len(obj.data.polygons)})
    ground_objects(objects);lo,hi=bounds(objects);extent=assert_dimensions(list(lo),list(hi),'plant')
    col=move_to_collection(objects,'Studio_PottedPlant')
    return col,{'source':'Poly Haven potted_plant_02','license':'CC0-1.0','soil_reduction':reductions,
                'leaf_geometry_preserved':True,'bounds_z_up_m':[list(lo),list(hi)],'dimensions_m':extent}


def load_reused(root,key,kind):
    root=Path(root);report=json.loads((root/'asset-export.json').read_text(encoding='utf8'))
    path=root/'models'/(key+'.glb');record=report['assets'][key]
    if sha(path)!=record['sha256']:raise ValueError('Reused native export changed')
    objects=import_gltf(path);ground_objects(objects);lo,hi=bounds(objects)
    extent=assert_dimensions(list(lo),list(hi),kind)
    col=move_to_collection(objects,'Studio_'+key)
    return col,{**record,'reused_from_commit':'46ad223ff7d8ae0ccbb6e2913d37ebfb2ba0526d',
                'bounds_z_up_m':[list(lo),list(hi)],'dimensions_m':extent,'input_glb_sha256':sha(path)}


def prepare(assets,people,legacy):
    evidence={'source_download_files_verified':verify_downloads(assets),'people_download_files_verified':verify_downloads(people)}
    kit={};rigs=[]
    kit['car']=load_reused(legacy,'car','car');kit['tree']=load_reused(legacy,'tree','tree')
    kit['bench']=reviewed_bench(assets);kit['plant']=reviewed_plant(assets)
    for name,prefix,key in [('Business_Male_01','m005','male'),('Business_Female_01','f014','female')]:
        col,rig,meta=business_avatar(people,name,prefix);kit[key]=(col,meta);rigs.append(rig)
    return kit,rigs,evidence
