import copy
import pytest
from PIL import Image
from jevdrive.media_validation import image_sequence, unchanged_frames, validate_decoded_probe


def frames(tmp_path):
    for i in (1,2,3): Image.new('RGB',(32,18)).save(tmp_path/f'frame_{i:04d}.png')
    return image_sequence(tmp_path,3,32,18)


def test_verify_every_frame_and_detect_later_changes(tmp_path):
    records=frames(tmp_path)
    unchanged_frames(tmp_path,records)
    (tmp_path/'frame_0002.png').write_bytes(b'changed')
    with pytest.raises(ValueError): unchanged_frames(tmp_path,records)


@pytest.mark.parametrize('problem',['missing','extra','wrong_size','corrupt'])
def test_bad_sequence_refused(tmp_path,problem):
    frames(tmp_path)
    if problem=='missing': (tmp_path/'frame_0002.png').unlink()
    if problem=='extra': Image.new('RGB',(32,18)).save(tmp_path/'frame_0004.png')
    if problem=='wrong_size': Image.new('RGB',(16,16)).save(tmp_path/'frame_0002.png')
    if problem=='corrupt': (tmp_path/'frame_0002.png').write_bytes(b'not a png')
    with pytest.raises((ValueError,OSError)): image_sequence(tmp_path,3,32,18)


def probe():
    return {'streams':[{'codec_name':'h264','width':1920,'height':1080,
                        'avg_frame_rate':'30/1','nb_read_frames':'180'}],
            'format':{'duration':'6.000000'}}


def test_actual_decode_count_required():
    p=probe(); assert validate_decoded_probe(p,180,1920,1080,30)
    p['streams'][0]['nb_frames']='180'; del p['streams'][0]['nb_read_frames']
    with pytest.raises(ValueError): validate_decoded_probe(p,180,1920,1080,30)


@pytest.mark.parametrize('field,value',[('codec_name','hevc'),('width',960),('height',540),
    ('avg_frame_rate','24/1'),('avg_frame_rate','0/0'),('nb_read_frames','179')])
def test_decode_contract_rejects_wrong_media(field,value):
    p=probe(); p['streams'][0][field]=value
    with pytest.raises(ValueError): validate_decoded_probe(p,180,1920,1080,30)


@pytest.mark.parametrize('duration',['nan','inf','6.5'])
def test_invalid_duration_rejected(duration):
    p=probe(); p['format']['duration']=duration
    with pytest.raises(ValueError): validate_decoded_probe(p,180,1920,1080,30)


def test_multiple_streams_rejected():
    p=probe(); p['streams'].append(copy.deepcopy(p['streams'][0]))
    with pytest.raises(ValueError): validate_decoded_probe(p,180,1920,1080,30)
