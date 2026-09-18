"""Native importer diagnostics; no claim of completed asset integration."""
import argparse,json,sys,math
from pathlib import Path
import bpy
from mathutils import Vector

p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--people',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=True);rows=[]
paths=[('car',a.assets/'bmw/source/bmw.obj'),('tree',a.assets/'tree_small_02/tree_small_02.gltf'),('bench',a.assets/'modular_street_seating/modular_street_seating.gltf'),('plant',a.assets/'potted_plant_02/potted_plant_02.gltf')]
paths += [(n,a.people/n/'Export'/(n+'.fbx')) for n in ['Business_Male_01','Business_Female_01']]
for name,path in paths:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix=='.obj':bpy.ops.wm.obj_import(filepath=str(path.resolve()))
    elif path.suffix=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path.resolve()),use_image_search=True)
    else:bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    objects=[]
    for o in bpy.context.scene.objects:
        row={'name':o.name,'type':o.type,'location':list(o.location),'rotation':list(o.rotation_euler),'scale':list(o.scale)}
        if o.type=='MESH':
            o.data.calc_loop_triangles();row['triangles']=len(o.data.loop_triangles)
            pts=[o.matrix_world@Vector(v) for v in o.bound_box];row['bounds']=[[min(v[i] for v in pts) for i in range(3)],[max(v[i] for v in pts) for i in range(3)]]
            row['materials']=[m.name if m else None for m in o.data.materials]
        elif o.type=='ARMATURE':row['bones']=[{'name':b.name,'head':list(b.head_local),'tail':list(b.tail_local)} for b in o.data.bones]
        objects.append(row)
    materials=[]
    for m in bpy.data.materials:
        if not m.use_nodes:continue
        materials.append({'name':m.name,'images':[{'name':n.image.name,'path':n.image.filepath} for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image]})
    result={'id':name,'objects':objects,'materials':materials,'actions':[x.name for x in bpy.data.actions]};rows.append(result)
    print(json.dumps(result),flush=True)
(a.out/'native-import-inspection.json').write_text(json.dumps({'blender':bpy.app.version_string,'assets':rows},indent=2),encoding='utf8')
print('NATIVE_IMPORTS_COMPLETE',flush=True)
