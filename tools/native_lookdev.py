"""Optional authored look-development; no measured street geometry is changed."""
from __future__ import annotations
import math


def paving_uv(x, y, origin, forward, repeat_m):
    values=(x,y,*origin,*forward,repeat_m)
    if any(isinstance(v,bool) or not math.isfinite(v) for v in values):
        raise ValueError('UV inputs must be finite numbers')
    length=math.hypot(*forward)
    if length<1e-6 or not .1<=repeat_m<=20:
        raise ValueError('Invalid paving orientation or scale')
    tx,ty=forward[0]/length,forward[1]/length
    dx,dy=x-origin[0],y-origin[1]
    return ((dx*ty-dy*tx)/repeat_m,(dx*tx+dy*ty)/repeat_m)


def grate_segments(half=.70, opening=.28, pitch=.09, bar=.022):
    if not 0<bar<pitch<opening<half or half>2:
        raise ValueError('Invalid grate dimensions')
    boxes=[]
    for i in range(-int((half-bar)/pitch),int((half-bar)/pitch)+1):
        x=i*pitch
        ranges=[(-half,-opening),(opening,half)] if abs(x)<opening+bar/2 else [(-half,half)]
        for low,high in ranges:
            boxes.extend([(x-bar/2,low,x+bar/2,high),(low,x-bar/2,high,x+bar/2)])
    boxes.extend([(-half-.06,-half-.06,half+.06,-half),(-half-.06,half,half+.06,half+.06),
                  (-half-.06,-half,-half,half),(half,-half,half+.06,half)])
    return boxes


def configure_lighting(scene, preset):
    if preset not in ('legacy','neutral-daylight'):
        raise ValueError('Unknown look preset')
    result={'preset':preset,'measured_local_weather':False}
    if preset=='neutral-daylight':
        scene.view_settings.exposure=.70
        scene.view_settings.look='AgX - Medium High Contrast'
        scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.85
        for light in scene.objects:
            if light.name=='Art_Direction_Sun':
                light.data.energy=.35
                light.data.angle=math.radians(1.0)
        if scene.render.engine=='BLENDER_EEVEE' and hasattr(scene.eevee,'use_fast_gi'):
            scene.eevee.use_fast_gi=True
    result['exposure_stops']=scene.view_settings.exposure
    result['world_strength']=scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value
    result['sun_energy']=next((o.data.energy for o in scene.objects if o.name=='Art_Direction_Sun'),None)
    result['colour_transform']=scene.view_settings.view_transform
    return result


def add_tree_grates(scene, placements, terrain_objects):
    import bpy
    from mathutils import Vector
    if not placements: raise ValueError('Tree grates require an explicit authored tree layer')
    collection=bpy.data.collections.new('AUTHORED_Tree_Grates_Not_Surveyed')
    scene.collection.children.link(collection)
    materials=[]
    for name,colour,rough,metal in [('CastIron',(.025,.032,.029,1),.62,.65),('Soil',(.042,.031,.021,1),.96,0)]:
        mat=bpy.data.materials.new('AUTHORED_'+name); mat.use_nodes=True
        bs=mat.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Base Color'].default_value=colour
        bs.inputs['Roughness'].default_value=rough; bs.inputs['Metallic'].default_value=metal
        mat['provenance']='Procedural visual supplement; not a surveyed Tokyo object'
        materials.append(mat)
    transforms=[(obj,obj.matrix_world.inverted()) for obj in terrain_objects]
    def surface(x,y):
        hits=[]
        for obj,inv in transforms:
            hit,pos,_,_=obj.ray_cast(inv @ Vector((x,y,1000)),(inv.to_3x3() @ Vector((0,0,-1))).normalized())
            if hit: hits.append((obj.matrix_world @ pos).z)
        if not hits: raise ValueError('Authored grate extends beyond source road coverage')
        return max(hits)
    records=[]
    for item in placements:
        if item.get('osm_node_id'): raise ValueError('Grates must not masquerade as mapped objects')
        cx,cy,z=item['xyz']; verts=[]; faces=[]; slots=[]
        def box(rect,height,slot):
            x0,y0,x1,y1=rect; base=len(verts)
            corners=[(cx+x0,cy+y0),(cx+x1,cy+y0),(cx+x1,cy+y1),(cx+x0,cy+y1)]
            ground=[surface(x,y) for x,y in corners]
            for dz in (.006,height):
                verts.extend((x,y,g+dz) for (x,y),g in zip(corners,ground))
            for ids in ((0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)):
                faces.append(tuple(base+i for i in ids)); slots.append(slot)
        for rect in grate_segments(): box(rect,.038,0)
        box((-.28,-.28,.28,.28),.012,1)
        mesh=bpy.data.meshes.new('AuthoredGrateMesh_'+item['id'])
        mesh.from_pydata(verts,[],faces); mesh.update()
        obj=bpy.data.objects.new('AUTHORED_Grate_'+item['id'],mesh)
        collection.objects.link(obj)
        for mat in materials: mesh.materials.append(mat)
        for polygon,slot in zip(mesh.polygons,slots): polygon.material_index=slot
        bevel=obj.modifiers.new('ManufacturedEdge','BEVEL'); bevel.width=.002; bevel.segments=2
        obj['provenance']='Authored tree root dressing, not mapped infrastructure or collision geometry'
        obj['source_tree_id']=item['id']; obj['visual_only']=True
        obj['offset_above_source_surface_m']=.038
        records.append({'id':obj.name,'tree_id':item['id'],'vertices':len(verts),'faces':len(faces),
                        'source_ground_sampled':True,'top_offset_m':.038,'surveyed':False,'physics_actor':False})
    return records


def material_snapshot(scene):
    """Record imported surface shader values and texture sizes, not guessed quality."""
    result={}
    for obj in scene.objects:
        if obj.type!='MESH' or not obj.name.startswith(('public_building_','detail_tran_')): continue
        for mat in obj.data.materials:
            if mat is None or not mat.use_nodes or mat.name in result: continue
            shaders=[]; images=[]
            for node in mat.node_tree.nodes:
                if node.type=='BSDF_PRINCIPLED':
                    values={}
                    for key in ('Base Color','Roughness','Metallic'):
                        socket=node.inputs[key]; value=socket.default_value
                        values[key]={'value':float(value) if isinstance(value,(int,float)) else list(value),
                            'links':sorted((link.from_node.name,link.from_socket.name) for link in socket.links)}
                    shaders.append({'node':node.name,'inputs':values})
                if node.type=='TEX_IMAGE' and node.image:
                    images.append({'node':node.name,'image':node.image.name,'size':list(node.image.size)})
            result[mat.name]={'shaders':shaders,'images':sorted(images,key=lambda r:r['node'])}
    return result
