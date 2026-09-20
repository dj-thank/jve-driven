"""Produce an attributed video and frame/pose evidence without changing the viewpoint."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np


def encode(root: Path):
    record = json.loads((root/'capture.json').read_text(encoding='utf8'))
    render = json.loads((root/'render-evidence.json').read_text(encoding='utf8'))
    if not render['completed'] or render['capture_sha256'] != hashlib.sha256((root/'capture.json').read_bytes()).hexdigest():
        raise ValueError('Incomplete or mismatched capture evidence')
    spec = record['camera']; width, height = spec['width'], spec['height']
    if len(render['frames']) != spec['fps']*spec['seconds']:
        raise ValueError('Missing frames')
    output = root/'delivery'; output.mkdir(exist_ok=False)
    labels = root/'labeled'; labels.mkdir(exist_ok=False)
    fontpath = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    title = ImageFont.truetype(fontpath, 19); text = ImageFont.truetype(fontpath, 13)
    signature = []
    for index, proof in enumerate(render['frames']):
        data = (root/'frames'/f'{index:05d}.png').read_bytes()
        if hashlib.sha256(data).hexdigest() != proof['sha256']: raise ValueError('Rendered frame changed')
        image = Image.open(root/'frames'/f'{index:05d}.png').convert('RGB')
        if image.size != (width, height): raise ValueError('Wrong frame dimensions')
        a = np.asarray(image); signature.append(float(a.std()))
        draw = ImageDraw.Draw(image, 'RGBA')
        draw.rectangle((0, 0, width, 67), fill=(6, 13, 18, 215))
        draw.text((19, 10), 'TOKYO / PUBLIC-DATA EGO CAMERA', font=title, fill=(241, 248, 248))
        draw.text((19, 38), f"3D INSPECTION - NOT AUTONOMOUS DRIVING | Jev control: OFF | t={index/spec['fps']:05.2f}s", font=text, fill=(244, 205, 146))
        draw.rectangle((0, height-61, width, height), fill=(6, 13, 18, 215))
        draw.text((19, height-53), 'City/ortho: MLIT PLATEAU / Tokyo 2025 | Terrain: Mapterhorn / GSI | Route: OpenStreetMap contributors', font=text, fill=(235, 243, 244))
        draw.text((19, height-29), 'Processed by Jev Drive Lab. Source textures; no AI-generated facades. Camera height 1.55 m / horizontal FOV 80 deg.', font=text, fill=(191, 211, 217))
        image.save(labels/f'{index:05d}.png')
        if index in (0, len(render['frames'])//2, len(render['frames'])-1):
            image.save(output/f'ego-frame-{index:05d}.png')
    video = output/'tokyo-ego-public-world.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(spec['fps']), '-i', str(labels/'%05d.png'),
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', str(video)], check=True, timeout=180)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]))
    stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    if int(stream['nb_frames']) != len(render['frames']) or abs(float(probe['format']['duration'])-spec['seconds']) > .1:
        raise ValueError('Encoded duration/frame mismatch')
    report = {'schema': 'jevdrive.ego-video.v1', 'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
              'scene_sha256': record['scene_sha256'], 'capture_sha256': render['capture_sha256'],
              'actual_blender_execution': True, 'renderer': render['renderer'],
              'width': width, 'height': height, 'fps': spec['fps'], 'frames': len(render['frames']),
              'duration_s': float(probe['format']['duration']), 'frame_pixel_std_min': min(signature),
              'route_osm_id': record['route']['osm_way_id'], 'layers': record['source_manifest']['layers'],
              'camera_inspection_only': True, 'live_jev_calls': 0, 'controller_executed': False,
              'photorealism_verified': False, 'real_world_geometric_accuracy_verified': False}
    (output/'video-evidence.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    for name in ['capture.json', 'capture.sha256', 'render-evidence.json']:
        shutil.copyfile(root/name, output/name)
    license_path = Path(__file__).resolve().parents[1]/'docs/EGO_DATA_LICENSES.md'
    shutil.copyfile(license_path, output/'DATA-LICENSES.md')
    print(json.dumps({k:v for k,v in report.items() if k != 'layers'}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('capture', type=Path)
    encode(p.parse_args().capture)
