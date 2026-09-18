"""Synthetic placement tests; not measured Tokyo trees or driving evidence."""
import copy
import math
import pytest
from shapely.geometry import LineString
from jevdrive.visual_enrichment import authored_tree_layer, validate_tree_layer


def example():
    plan={'source_glb_sha256':'b'*64,'driveable':False,'jev_calls':0,
          'frames':[{'xyz':[0,30,1.55]},{'xyz':[0,70,1.55]}]}
    route=LineString([(0,0),(0,200)])
    return plan, route


def test_repeatable_and_separate_from_truth():
    plan,route=example(); before=copy.deepcopy(plan)
    a=authored_tree_layer(plan,route,lambda x,y:0.,plan_sha256='a'*64)
    b=authored_tree_layer(plan,route,lambda x,y:0.,plan_sha256='a'*64)
    assert a==b and plan==before
    assert validate_tree_layer(a,plan,'a'*64)==a['trees']
    assert not a['driveable'] and not a['traffic_actor'] and not a['changes_source_geometry']
    assert all(x['osm_node_id'] is None and x['placement_source']=='AUTHORED_NOT_SURVEYED' for x in a['trees'])


def test_exact_height_function_and_missing_coverage():
    plan,route=example()
    def surface(x,y):
        if x<0: raise ValueError('Not covered')
        return x*.1+y*.01
    a=authored_tree_layer(plan,route,surface,plan_sha256='a'*64)
    assert a['rejected']
    assert all(t['xyz'][2]==pytest.approx(t['xyz'][0]*.1+t['xyz'][1]*.01) for t in a['trees'])


@pytest.mark.parametrize('damage',['hash','source','truth','traffic','duplicate','nan','bool','size'])
def test_corrupted_or_false_attribution_rejected(damage):
    plan,route=example()
    layer=authored_tree_layer(plan,route,lambda x,y:0.,plan_sha256='a'*64)
    if damage=='hash': layer['plan_sha256']='c'*64
    if damage=='source': layer['source_glb_sha256']='c'*64
    if damage=='truth': layer['trees'][0]['osm_node_id']='123'
    if damage=='traffic': layer['traffic_actor']=True
    if damage=='duplicate': layer['trees'].append(copy.deepcopy(layer['trees'][0]))
    if damage=='nan': layer['trees'][0]['xyz'][2]=math.nan
    if damage=='bool': layer['trees'][0]['xyz'][0]=True
    if damage=='size': layer['trees'][0]['height_m']=1000
    with pytest.raises(ValueError): validate_tree_layer(layer,plan,'a'*64)


@pytest.mark.parametrize('spacing,offset',[(0,6),(100,6),(12,0),(12,100),(math.nan,6)])
def test_placement_budget(spacing,offset):
    plan,route=example()
    with pytest.raises(ValueError):
        authored_tree_layer(plan,route,lambda x,y:0.,plan_sha256='a'*64,spacing_m=spacing,offset_m=offset)


def test_nonfinite_height_is_not_replaced_with_zero():
    plan,route=example()
    with pytest.raises(ValueError): authored_tree_layer(plan,route,lambda x,y:math.nan,plan_sha256='a'*64)
