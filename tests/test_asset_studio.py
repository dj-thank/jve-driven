"""Asset-studio contracts. These tests never make network calls or certify realism."""
import hashlib,io,json,math,sys
from pathlib import Path
import pytest

TOOLS=Path(__file__).resolve().parents[1]/'tools/asset_studio'
sys.path.insert(0,str(TOOLS))
from validation import resolve_inside,verify_downloads,finite_bounds,assert_dimensions,wheel_roll,frame_clock,assert_font_free
from acquire import Store,safe_url,safe_path


@pytest.mark.parametrize('path',['../outside','/absolute','C:/drive','a/../../b','a\\..\\..\\b',''])
def test_unsafe_asset_path_rejected(tmp_path,path):
    with pytest.raises(ValueError):resolve_inside(tmp_path,path)


def test_nested_asset_path_is_portable(tmp_path):
    assert resolve_inside(tmp_path,'model\\textures\\base.jpg')==tmp_path/'model/textures/base.jpg'


@pytest.mark.parametrize('url',['http://api.polyhaven.com/a','https://example.org/a','https://api.polyhaven.com.example.org/a','https://u:p@api.polyhaven.com/a','https://api.polyhaven.com:444/a'])
def test_download_does_not_leave_reviewed_hosts(url):
    with pytest.raises(ValueError):safe_url(url)


def locked_fixture(root):
    data=b'synthetic-model';(root/'model.glb').write_bytes(data)
    row={'path':'model.glb','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    (root/'download-lock.json').write_text(json.dumps({'resources':[row]}),encoding='utf8');return row


def test_lock_checks_actual_bytes(tmp_path):
    locked_fixture(tmp_path);assert verify_downloads(tmp_path)==1
    (tmp_path/'model.glb').write_bytes(b'wrong')
    with pytest.raises(ValueError):verify_downloads(tmp_path)


@pytest.mark.parametrize('damage',['duplicate','outside','size','empty'])
def test_invalid_source_manifest(tmp_path,damage):
    row=locked_fixture(tmp_path);rows=[row]
    if damage=='duplicate':rows.append(row)
    elif damage=='outside':row['path']='../model.glb'
    elif damage=='size':row['bytes']=True
    else:rows=[]
    (tmp_path/'download-lock.json').write_text(json.dumps({'resources':rows}),encoding='utf8')
    with pytest.raises(ValueError):verify_downloads(tmp_path)


@pytest.mark.parametrize('lo,hi',[((),(1,2,3)),((0,0,0),(1,2,math.nan)),((0,0,0),(0,0,0)),((1,0,0),(0,1,1)),((False,0,0),(1,2,3))])
def test_invalid_bounds(lo,hi):
    with pytest.raises(ValueError):finite_bounds(lo,hi)


@pytest.mark.parametrize('kind,lo,hi',[
 ('car',(-1,-2.375,0),(1,2.375,1.55)),
 ('person',(-.4,-.18,0),(.4,.18,1.8)),
 ('tree',(-2,-2,0),(2,2,6.5)),
 ('bench',(-1.25,-.3,0),(1.25,.4,.9)),
 ('plant',(-.4,-.4,0),(.4,.4,.9))])
def test_expected_metric_scale(kind,lo,hi):
    assert len(assert_dimensions(lo,hi,kind))==3


@pytest.mark.parametrize('kind,lo,hi',[
 ('car',(-100,-237,0),(100,237,155)),
 ('car',(-1,-2.3,.2),(1,2.3,1.7)),
 ('person',(-.4,-.2,0),(.4,.2,.8)),
 ('unknown',(0,0,0),(1,1,1))])
def test_bad_scale_or_floating_asset_rejected(kind,lo,hi):
    with pytest.raises(ValueError):assert_dimensions(lo,hi,kind)


def test_wheel_circumference_and_direction():
    assert wheel_roll(2*math.pi*.35,.35)==pytest.approx(-2*math.pi)
    assert wheel_roll(0,.35)==0


@pytest.mark.parametrize('d,r',[(math.nan,.3),(1,0),(1,True),(1,.9)])
def test_invalid_wheel_travel(d,r):
    with pytest.raises(ValueError):wheel_roll(d,r)


def test_clock_is_frame_exact():
    rows=frame_clock(300,30);assert rows[0]=={'frame':1,'time_s':0}
    assert rows[-1]['time_s']==pytest.approx(299/30)


@pytest.mark.parametrize('n,fps',[(True,30),(0,30),(901,30),(300,0),(300,30.0)])
def test_invalid_schedule(n,fps):
    with pytest.raises(ValueError):frame_clock(n,fps)


@pytest.mark.parametrize('extension',['ttf','OTF','woff2'])
def test_no_font_redistribution(tmp_path,extension):
    (tmp_path/('not-a-real-font.'+extension)).write_bytes(b'fixture')
    with pytest.raises(ValueError):assert_font_free(tmp_path)


def test_models_not_fonts(tmp_path):
    (tmp_path/'scene.glb').write_bytes(b'fixture');assert assert_font_free(tmp_path)


class Response(io.BytesIO):
    def __init__(self,data):super().__init__(data);self.headers={'Content-Length':str(len(data))}
class Opener:
    def __init__(self,data):self.data=data
    def open(self,request,timeout):
        assert not request.has_header('Authorization')
        return Response(self.data)


def test_real_download_contract_with_fake_transport(tmp_path):
    data=b'fixture';s=Store(tmp_path/'out');s.opener=Opener(data)
    assert s.fetch('https://api.polyhaven.com/test','test.bin',{'size':len(data),'md5':hashlib.md5(data).hexdigest()})==data
    assert verify_downloads(s.root)==1


@pytest.mark.parametrize('expected',[{'size':100},{'md5':'0'*32}])
def test_publisher_mismatch_is_not_saved(tmp_path,expected):
    s=Store(tmp_path/'out');s.opener=Opener(b'fixture')
    with pytest.raises(ValueError):s.fetch('https://api.polyhaven.com/test','test.bin',expected)
    assert not (s.root/'test.bin').exists()


def test_preserve_existing_directory(tmp_path):
    target=tmp_path/'out';target.mkdir();(target/'keep').write_text('keep',encoding='utf8')
    with pytest.raises(FileExistsError):Store(target)
    assert (target/'keep').read_text(encoding='utf8')=='keep'
