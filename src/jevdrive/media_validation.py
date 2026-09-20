"""Validate native images and decoded media; frame rate is not renderer speed."""
from __future__ import annotations
import hashlib
import math
from fractions import Fraction
from pathlib import Path
from PIL import Image


def image_sequence(directory, count, width, height):
    if type(count) is not int or not 1 <= count <= 1800:
        raise ValueError('Invalid bounded frame count')
    root=Path(directory)
    names=[f'frame_{i:04d}.png' for i in range(1,count+1)]
    if sorted(p.name for p in root.glob('frame_*.png'))!=names:
        raise ValueError('Missing or extra native frames')
    records=[]
    for name in names:
        path=root/name
        with Image.open(path) as image:
            if image.format!='PNG' or image.size!=(width,height):
                raise ValueError('Frame dimensions or format differ')
            image.verify()
        records.append({'name':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return records


def unchanged_frames(directory, records):
    for item in records:
        path=Path(directory)/item['name']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Native image changed during video packaging')


def validate_decoded_probe(probe, count, width, height, fps):
    streams=probe.get('streams',[])
    if len(streams)!=1: raise ValueError('Expected one decoded video stream')
    stream=streams[0]
    try:
        rate=Fraction(stream['avg_frame_rate'])
        duration=float(probe['format']['duration'])
        actual=int(stream['nb_read_frames'])
    except (KeyError,ValueError,TypeError,ZeroDivisionError) as exc:
        raise ValueError('Invalid decoded video evidence') from exc
    if (stream.get('codec_name')!='h264' or stream.get('width')!=width or
            stream.get('height')!=height or actual!=count or rate!=Fraction(str(fps)) or
            not math.isfinite(duration) or abs(duration-count/fps)>.02):
        raise ValueError('Encoded video does not match native frames and clock')
    return True
