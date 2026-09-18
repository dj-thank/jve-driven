"""Synthetic projection/terrain contracts, not real city or sensor validation."""
from dataclasses import replace
import math
import numpy as np
import pytest
from jevdrive.egoview import CameraSpec, camera_to_enu, sample_heights, select_camera_path
from jevdrive.publicworld.geo import Area, Frame


@pytest.mark.parametrize('kw', [{'fps':True}, {'width':1279}, {'height':-1}, {'seconds':0},
                                {'horizontal_fov_deg':float('nan')}, {'speed_mps':0},
                                {'height_above_surface_m':20}, {'horizontal_fov_deg':179}])
def test_camera_rejects_invalid_settings(kw):
    with pytest.raises(ValueError): CameraSpec(**kw)


@pytest.mark.parametrize('yaw', [0, .7, 2, -2])
def test_forward_point_projects_to_center_and_right_to_right(yaw):
    spec = CameraSpec(); pose = camera_to_enu([12, 30, 50], yaw)
    np.testing.assert_allclose(pose[:3,:3].T @ pose[:3,:3], np.eye(3), atol=1e-12)
    assert np.linalg.det(pose[:3,:3]) == pytest.approx(1)
    for x in [0, 2]:
        world = pose @ [x, 0, 10, 1]
        camera = np.linalg.inv(pose) @ world
        pixel = np.array(spec.intrinsic) @ camera[:3]
        np.testing.assert_allclose(pixel[:2]/pixel[2], [640+spec.intrinsic[0][0]*x/10, 360], atol=1e-9)


def test_blender_conversion_preserves_forward_and_up():
    p = camera_to_enu([0,0,0], 0)
    blender = p @ np.diag([1,-1,-1,1])
    np.testing.assert_allclose(blender @ [0,0,-1,0], [1,0,0,0])
    np.testing.assert_allclose(blender @ [0,1,0,0], [0,0,1,0])


def test_barycentric_heights_not_nearest_vertex():
    t = np.array([[[0,0,40],[10,0,50],[0,10,60]]])
    np.testing.assert_allclose(sample_heights(t, [[1,2],[0,0]]), [45,40])
    assert np.isnan(sample_heights(t, [[11,11]])[0])


def test_multilevel_requires_selection():
    t = np.array([[[0,0,40],[10,0,40],[0,10,40]], [[0,0,45],[10,0,45],[0,10,45]]])
    with pytest.raises(ValueError, match='Multiple'): sample_heights(t, [[1,1]])


def fixture():
    area = Area(139.763,35.680,139.765,35.682); frame = Frame(139.764,35.681)
    roads = {'features':[{'id':'real-format-test-only','properties':{'osm_tags':{'highway':'residential'}},
                         'geometry':{'type':'LineString','coordinates':[[139.7632,35.681],[139.7648,35.681]]}}]}
    terrain = np.array([[[-200,-200,40],[200,-200,40],[200,200,40]],
                        [[-200,-200,40],[200,200,40],[-200,200,40]]])
    return roads,area,frame,terrain


def test_camera_plan_is_metric_continuous_and_explicitly_not_driving():
    roads,area,frame,terrain = fixture(); spec = CameraSpec()
    result = select_camera_path(roads,area,frame,terrain,spec)
    frames = result['route']['frames']
    assert len(frames) == 96 and frames[-1]['time_s'] == 95/12
    assert not result['controller_executed'] and not result['driveable'] and result['live_jev_calls'] == 0
    poses = np.array([p['position_enu_m'] for p in frames])
    np.testing.assert_allclose(poses[:,2], 41.55)
    np.testing.assert_allclose(np.linalg.norm(np.diff(poses,axis=0),axis=1), .25, atol=1e-6)


def test_missing_surface_is_never_filled_flat():
    roads,area,frame,terrain = fixture()
    with pytest.raises(ValueError, match='No continuous'):
        select_camera_path(roads,area,frame,terrain+1000,CameraSpec())


def test_bridge_is_not_draped_on_terrain():
    roads,area,frame,terrain = fixture(); roads['features'][0]['properties']['osm_tags']['bridge']='yes'
    with pytest.raises(ValueError): select_camera_path(roads,area,frame,terrain,CameraSpec())


def test_real_road_mesh_when_aligned():
    roads,area,frame,terrain = fixture()
    road = terrain.astype(float); road[:,:,2] += .3
    r = select_camera_path(roads,area,frame,terrain,CameraSpec(),road)
    assert r['route']['surface_source'].startswith('public_road_mesh')
    assert r['route']['frames'][0]['position_enu_m'][2] == pytest.approx(41.85)


def test_no_fake_calibration_claim():
    assert CameraSpec().record()['calibration_source'] == 'configured_virtual_sensor_not_measured_camera'
