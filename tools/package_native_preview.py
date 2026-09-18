"""Encode completed native frames with permanent provenance/no-Jev labels."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from jevdrive.media_validation import image_sequence, unchanged_frames, validate_decoded_probe

def file_hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--render',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--font',type=Path,required=True,help='Local font; never copied into outputs')
    a=p.parse_args(); source=a.render.resolve()
    report=json.loads((source/'render-report.json').read_text(encoding='utf8'))
    frames=sorted((source/'frames').glob('frame_*.png'))
    expected=[f'frame_{i:04d}.png' for i in range(1,report['frames_rendered']+1)]
    if [f.name for f in frames]!=expected: raise ValueError('Missing/extra native frames')
    if report['jev_calls']!=0 or report['driveable'] or report['physics_simulated']:
        raise ValueError('This packager labels only visual inspections, not API-driving results')
    frame_records=image_sequence(source/'frames',report['frames_rendered'],report['width'],report['height'])
    if a.out.exists(): raise FileExistsError('Use a fresh evidence destination')
    a.out.mkdir(parents=True); out=a.out.resolve()
    width,height=report['width'],report['height']; overlay=Image.new('RGBA',(width,height))
    draw=ImageDraw.Draw(overlay); font=ImageFont.truetype(str(a.font),22)
    small=ImageFont.truetype(str(a.font),17)
    draw.rounded_rectangle((24,20,1010,70),radius=8,fill=(7,17,23,205))
    title='実都市データの車載視点検査 | 質感補完あり | Jev未接続・自動運転ではありません'
    if not report.get('generic_paving_albedo'):
        title='実都市データの車載視点検査 | 航空写真を再投影 | Jev未接続・自動運転ではありません'
    if report.get('authored_tree_count',0):
        title='実都市の車載視点 | 舗装・樹木配置は補完 | Jev未接続・自動運転ではありません'
    if report.get('authored_tree_grates'):
        title='実都市の車載視点 | 舗装・樹木・根元造作は補完 | Jev未接続・自動運転ではありません'
    draw.text((40,31),title,font=font,fill='white')
    draw.rectangle((0,height-62,width,height),fill=(7,17,23,220))
    draw.text((22,height-55),'国土交通省 PLATEAU 千代田区2025等を加工 / © OpenStreetMap contributors / 地形: PLATEAU・Mapterhorn・国土地理院',font=small,fill='white')
    draw.text((22,height-30),'空・補完素材: Poly Haven (CC0) / 近距離の壁面解像度・現地との精度は未検証 / 30fpsは動画の再生設定',font=small,fill='white')
    overlay_path=out/'provenance-overlay.png'; overlay.save(overlay_path)
    with Image.open(frames[0]) as image:
        if image.size!=(width,height): raise ValueError('Frame dimensions differ from native report')
        shown=Image.alpha_composite(image.convert('RGBA'),overlay).convert('RGB')
        shown.save(out/'tokyo-ego-quality.png')
        shown.thumbnail((1280,720)); shown.save(out/'tokyo-ego-quality.jpg',quality=92)
    video=out/'tokyo-ego-quality.mp4'
    command=[shutil.which('ffmpeg') or 'ffmpeg','-nostdin','-n','-loglevel','error',
        '-framerate',str(report['fps']),'-i',str(source/'frames/frame_%04d.png'),
        '-i',str(overlay_path),'-filter_complex','[0:v][1:v]overlay=0:0:format=auto[v]',
        '-map','[v]','-an','-c:v','libx264','-preset','medium','-crf','18',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
    subprocess.run(command,check=True,timeout=300)
    probe=json.loads(subprocess.check_output([shutil.which('ffprobe') or 'ffprobe',
        '-v','error','-count_frames','-show_entries','stream=codec_name,width,height,avg_frame_rate,nb_frames,nb_read_frames:format=duration,size',
        '-of','json',str(video)],timeout=30))
    validate_decoded_probe(probe,len(frames),width,height,report['fps'])
    subprocess.run([shutil.which('ffmpeg') or 'ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True,timeout=90)
    unchanged_frames(source/'frames',frame_records)
    stream=probe['streams'][0]
    if (int(stream['nb_frames'])!=len(frames) or stream['width']!=width or stream['height']!=height
            or abs(float(probe['format']['duration'])-len(frames)/report['fps'])>.02):
        raise ValueError('Encoded video failed frame/duration/dimension validation')
    shutil.copy2(source/'render-report.json',out/'render-report.json')
    if report.get('material_audit_sha256'):
        if file_hash(source/'material-audit.json')!=report['material_audit_sha256']:
            raise ValueError('Material evidence changed since native render')
        shutil.copy2(source/'material-audit.json',out/'material-audit.json')
    evidence={'schema':'jevdrive.native-media-evidence.v1','video_sha256':file_hash(video),
        'overlay_sha256':file_hash(overlay_path),'video':probe,'native_render':report,
        'packager_sha256':file_hash(__file__),
        'native_render_fps_including_setup':len(frames)/report['elapsed_s'],
        'realtime_rendering_claimed':False,'jev_calls':0,'physics_simulated':False,
        'all_pngs_decoded_and_verified':True,'full_h264_decode_passed':True,
        'source_frames_unchanged_after_encoding':True,'frames':frame_records}
    (out/'media-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    (out/'SOURCES.txt').write_text(
        'Research preview; not an autonomous-driving or Jev API execution recording.\n'
        'PLATEAU Chiyoda 2025 and terrain/orthophotos, processed and rendered.\n'
        'https://www.geospatial.jp/ckan/dataset/plateau-13101-chiyoda-ku-2025\n'
        'https://www.mlit.go.jp/plateau/site-policy/\n'
        'https://docs.plateauview.mlit.go.jp/datasets/terrain/\n'
        'https://docs.plateauview.mlit.go.jp/datasets/ortho/\n'
        'Road centerline: OpenStreetMap contributors, ODbL-1.0.\n'
        'https://www.openstreetmap.org/copyright\n'
        'Sky/optional paving: Poly Haven, CC0-1.0.\n'
        'https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky\n'
        'https://polyhaven.com/a/pavement_01\n'
        'https://polyhaven.com/license\n'
        'https://polyhaven.com/a/tree_small_02\n'
        'Paving pattern, optional authored tree placements/species, and lighting are not surveyed Tokyo appearance.\n'
        'Optional iron tree-root grates and soil are authored procedural appearance, not mapped Tokyo infrastructure.\n'
        'Do not infer geometric accuracy, real-time rendering or driving safety.\n',encoding='utf8')
    print(json.dumps({'output':str(out),'frames':len(frames),'video_sha256':evidence['video_sha256'],
                      'seconds':probe['format']['duration'],'bytes':probe['format']['size']},indent=2))

if __name__=='__main__': main()
