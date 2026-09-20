"""Export the actual source models separately from long-running scene renders."""
import argparse,json,sys,time,shutil
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from hero_asset_kit import build_kit,sha,bounds

def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=a.assets.resolve();out=a.out.resolve()
    if not bpy.app.background or out.exists():raise ValueError('Background run and new destination required')
    out.mkdir(parents=True);(out/'models').mkdir();bpy.ops.wm.read_factory_settings(use_empty=True)
    started=time.perf_counter();kit=build_kit(root);bpy.ops.file.pack_all();original=bpy.context.scene;inventory={}
    for key,(col,meta) in kit.items():
        scene=bpy.data.scenes.new('Export_'+key);scene.collection.children.link(col);bpy.context.window.scene=scene;scene.frame_set(1)
        output=out/'models'/(key+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',export_animations=False,export_apply=True)
        lo,hi=bounds(col.objects);triangles=0
        for o in col.objects:
            if o.type=='MESH':o.data.calc_loop_triangles();triangles+=len(o.data.loop_triangles)
        inventory[key]={**meta,'sha256':sha(output),'bytes':output.stat().st_size,'bounds_z_up_m':[list(lo),list(hi)],'triangles_before_export_modifiers':triangles,'export_axes':'glTF Y-up; metres'}
        bpy.context.window.scene=original;bpy.data.scenes.remove(scene)
    bpy.data.libraries.write(str(out/'models/hero-library.blend'),set(v[0] for v in kit.values()),fake_user=True,compress=True)
    for name in ['SOURCES.txt','download-lock.json','extracted-lock.json']:shutil.copy2(root/name,out/name)
    report={'schema':'jevdrive.native-hero-export.v1','completed':True,'blender':bpy.app.version_string,'native_geometry_export':True,'images_rendered':0,'assets':inventory,'source_lock_sha256':sha(root/'download-lock.json'),'kit_script_sha256':sha(Path(__file__).with_name('hero_asset_kit.py')),'script_sha256':sha(__file__),'elapsed_s':time.perf_counter()-started,'jev_calls':0,'physics_simulated':False,'photorealism_verified':False}
    (out/'asset-export.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
