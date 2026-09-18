"""Regression tests use synthetic fixtures, not live PLATEAU responses."""
import json
import shutil
import httpx
import pytest
from test_public_world import fake_client, config_file, BASE
from jevdrive.publicworld.pipeline import fetch_snapshot, build_snapshot
from jevdrive.publicworld.download import DownloadStore, verify_lock
from jevdrive.publicworld.integrity import verify_sources
from jevdrive.publicworld.audit import audit_snapshot


def fetched(tmp_path, roads=True):
    config = config_file(tmp_path, roads)
    out = tmp_path / 'snapshot'
    with fake_client() as client:
        fetch_snapshot(config, out, client=client)
    return config, out


@pytest.mark.parametrize('key', ['config', 'frame', 'building_tiles', 'imagery_tiles', 'terrain_tiles'])
def test_selection_changes_are_rejected(tmp_path, key):
    _, out = fetched(tmp_path)
    path = out / 'public-world.json'
    meta = json.loads(path.read_text(encoding='utf8'))
    if key == 'config':
        meta[key]['origin']['longitude'] += .0001
    elif key == 'frame':
        meta[key]['units'] = 'centimetres'
    elif key == 'building_tiles':
        meta[key][0]['transform_column_major'][12] += 10
    else:
        meta[key][0]['x'] += 1
    path.write_text(json.dumps(meta), encoding='utf8')
    with pytest.raises(ValueError, match='Source selection'):
        build_snapshot(out)


def test_roads_derived_file_is_sealed(tmp_path):
    _, out = fetched(tmp_path)
    (out / 'roads-centerlines.geojson').write_text('{}', encoding='utf8')
    with pytest.raises(ValueError, match='Derived source'):
        verify_sources(out)


def test_download_lock_metadata_is_sealed(tmp_path):
    _, out = fetched(tmp_path)
    path = out / 'download-lock.json'
    data = json.loads(path.read_text(encoding='utf8'))
    data['resources'][0]['url'] = BASE + 'changed'
    path.write_text(json.dumps(data), encoding='utf8')
    with pytest.raises(ValueError, match='Download lock changed'):
        verify_sources(out)


def test_duplicate_download_entries_rejected(tmp_path):
    _, out = fetched(tmp_path)
    path = out / 'download-lock.json'
    data = json.loads(path.read_text(encoding='utf8'))
    data['resources'].append(data['resources'][0])
    path.write_text(json.dumps(data), encoding='utf8')
    with pytest.raises(ValueError, match='Duplicate'):
        verify_lock(out)


def test_resume_reuses_verified_cache_without_network(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'cached'))) as client:
        store = DownloadStore(tmp_path, client=client)
        store.fetch(BASE + 'a')
    def forbidden(request):
        raise AssertionError('Cache hit must not make an HTTP request')
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        store = DownloadStore(tmp_path, client=client, resume=True)
        data, _ = store.fetch(BASE + 'a')
        assert data == b'cached' and store.used == 6


def test_resume_does_not_trust_corrupted_cache(tmp_path):
    _, out = fetched(tmp_path)
    raw = next((out / 'raw').iterdir())
    raw.write_bytes(b'corrupted')
    with pytest.raises(RuntimeError):
        DownloadStore(out, resume=True)


def test_resume_budget_cannot_be_reset(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'12345'))) as client:
        DownloadStore(tmp_path, client=client).fetch(BASE + 'a')
    with pytest.raises(ValueError, match='budget'):
        DownloadStore(tmp_path, max_bytes=4, resume=True)


def test_failed_fetch_can_resume_to_complete_snapshot(tmp_path):
    config = config_file(tmp_path)
    out = tmp_path / 'snapshot'
    with fake_client(missing='.png') as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_snapshot(config, out, client=client)
    original_paths = {p.name: p.read_bytes() for p in (out / 'raw').iterdir()}
    with fake_client() as client:
        meta = fetch_snapshot(config, out, client=client, resume=True)
    assert meta['stage'] == 'fetched'
    assert all((out / 'raw' / name).read_bytes() == value for name, value in original_paths.items())
    assert verify_sources(out) > 0
    build_snapshot(out)
    assert audit_snapshot(out)['driveable'] is False


def test_resume_rejects_config_drift_without_replacing_manifest(tmp_path):
    config = config_file(tmp_path)
    out = tmp_path / 'snapshot'
    with fake_client(missing='.png') as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_snapshot(config, out, client=client)
    original = (out / 'public-world.json').read_bytes()
    changed = json.loads(config.read_text(encoding='utf8'))
    changed['name'] = 'different dataset'
    config.write_text(json.dumps(changed), encoding='utf8')
    with pytest.raises(ValueError, match='config differs'):
        fetch_snapshot(config, out, resume=True)
    assert (out / 'public-world.json').read_bytes() == original


def test_complete_snapshot_is_not_refreshed_by_resume(tmp_path):
    config, out = fetched(tmp_path)
    with pytest.raises(ValueError, match='Only failed'):
        fetch_snapshot(config, out, resume=True)


def test_audit_reports_observed_texture_not_survey_accuracy(tmp_path):
    _, out = fetched(tmp_path)
    build_snapshot(out)
    report = audit_snapshot(out)
    assert report['textured_triangle_fraction'] == 1
    assert report['triangles'] >= 14
    # Fixture uses zoom 10 deliberately; no claim of high-resolution source data.
    assert report['ortho_nominal_pixel_spacing_m'] == pytest.approx(124.17631223854075)
    assert not report['geometric_accuracy_verified']
    assert not report['street_level_photorealism_verified']
    assert not report['driveable']
    assert report['road_centerlines'] == 1


def test_modified_export_rejected(tmp_path):
    _, out = fetched(tmp_path)
    build_snapshot(out)
    path = out / 'visual-world.glb'
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='GLB hash'):
        audit_snapshot(out)


def test_snapshot_portable_to_different_directory(tmp_path):
    _, out = fetched(tmp_path)
    target = tmp_path / 'relocated'
    shutil.copytree(out, target)
    build_snapshot(target)
    assert verify_sources(out) == verify_sources(target)
    assert audit_snapshot(target)['textured_triangle_fraction'] == 1
