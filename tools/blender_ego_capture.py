"""Render a verified ego inspection path in real Blender, with no imagined city assets."""
from __future__ import annotations
import argparse, hashlib, json, math, sys, time
from pathlib import Path


def main():
    import bpy
    from mathutils import Matrix
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not bpy.app.background:
        raise RuntimeError('Use background mode; an open user project will not be replaced')
    root = args.capture.resolve()
    data = (root/'capture.json').read_bytes()
    if hashlib.sha256(data).hexdigest() != (root/'capture.sha256').read_text().strip():
        raise ValueError('Capture manifest changed')
    record = json.loads(data)
    if record['mode'] != 'camera_inspection_not_driving' or record['driveable'] is not False:
        raise ValueError('This renderer does not certify closed-loop driving')
    glb = root/'ego-world.glb'
    if hashlib.sha256(glb.read_bytes()).hexdigest() != record['scene_sha256']:
        raise ValueError('Scene changed')
    frames_dir = root/'frames'
    if frames_dir.exists(): raise FileExistsError('Refusing to overwrite a previous render')
    frames_dir.mkdir()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.0
    # Original aerial photographs have baked lighting: do not double-shade them.
    photo_materials = 0
    for material in bpy.data.materials:
        if not material.use_nodes: continue
        nodes, links = material.node_tree.nodes, material.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if bsdf is None or output is None: continue
        if any(n.type == 'TEX_IMAGE' and n.image is not None for n in nodes):
            emission = nodes.new('ShaderNodeEmission')
            color = bsdf.inputs['Base Color']
            if color.is_linked:
                links.new(color.links[0].from_socket, emission.inputs['Color'])
            else:
                emission.inputs['Color'].default_value = color.default_value
            emission.inputs['Strength'].default_value = 1.0
            links.new(emission.outputs[0], output.inputs['Surface'])
            photo_materials += 1
        if hasattr(material, 'use_backface_culling'):
            material.use_backface_culling = True
    world = bpy.data.worlds.new('Assumed daylight, not a measured sky')
    world.use_nodes = True; scene.world = world
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.35, .50, .68, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .8
    light = bpy.data.lights.new('Assumed sun', 'SUN'); light.energy = 2.0; light.angle = math.radians(1)
    sun = bpy.data.objects.new('Assumed sun', light); scene.collection.objects.link(sun)
    sun.rotation_euler = (.45, -.3, -.5)
    camera_data = bpy.data.cameras.new('Calibrated forward camera')
    camera = bpy.data.objects.new('Calibrated forward camera', camera_data)
    scene.collection.objects.link(camera); scene.camera = camera
    spec = record['camera']
    camera_data.type = 'PERSP'; camera_data.sensor_fit = 'HORIZONTAL'; camera_data.sensor_width = 36
    camera_data.lens = 36/(2*math.tan(math.radians(spec['horizontal_fov_deg'])/2))
    camera_data.clip_start = .05; camera_data.clip_end = 3000
    camera_data.dof.use_dof = False
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 16
    scene.cycles.use_denoising = False; scene.cycles.seed = 41
    scene.render.use_persistent_data = True
    # Ubuntu Blender 4.0.2 is built without OpenImageDenoiser. Record this
    # explicitly and render more native samples; no AI detail is generated.
    scene.cycles.max_bounces = 2; scene.cycles.diffuse_bounces = 1; scene.cycles.glossy_bounces = 1
    scene.render.resolution_x = spec['width']; scene.render.resolution_y = spec['height']
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = 1; scene.render.pixel_aspect_y = 1
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGB'
    scene.render.fps = spec['fps']; scene.view_settings.view_transform = 'Standard'
    scene.view_settings.exposure = 0; scene.view_settings.gamma = 1
    scene.render.film_transparent = False
    # Blender camera local axes x=right,y=up,-z=forward, unlike optical axes.
    optical_to_blender = Matrix.Diagonal((1.0, -1.0, -1.0, 1.0))
    evidence = {'schema': 'jevdrive.blender-ego-render.v1', 'renderer': bpy.app.version_string,
                'engine': scene.render.engine, 'device': 'CPU', 'samples': 16, 'denoising': False,
                'denoising_note': 'Ubuntu 4.0.2 lacks OpenImageDenoiser; native Cycles samples only',
                'camera': spec, 'scene_sha256': record['scene_sha256'],
                'capture_sha256': hashlib.sha256(data).hexdigest(), 'photo_materials': photo_materials,
                'lighting': 'assumed daylight; source photograph materials use emission to avoid double lighting',
                'synthetic_city_geometry': False, 'controller_executed': False,
                'live_jev_calls': 0, 'frames': [], 'completed': False}
    started = time.monotonic()
    try:
        for frame in record['route']['frames']:
            camera.matrix_world = Matrix(frame['camera_to_enu']) @ optical_to_blender
            scene.frame_set(frame['frame']+1)
            scene.render.filepath = str(frames_dir/f"{frame['frame']:05d}.png")
            tick = time.monotonic(); bpy.ops.render.render(write_still=True)
            png = Path(scene.render.filepath).read_bytes()
            evidence['frames'].append({'frame': frame['frame'], 'sha256': hashlib.sha256(png).hexdigest(),
                                      'render_seconds': time.monotonic()-tick})
        evidence['completed'] = True
    finally:
        evidence['elapsed_seconds'] = time.monotonic()-started
        (root/'render-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in evidence.items() if k != 'frames'}), flush=True)


if __name__ == '__main__': main()
