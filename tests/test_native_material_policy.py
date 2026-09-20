"""Shader-policy/clock tests use objects, not a claimed native Blender render."""
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

path=Path(__file__).parents[1]/'tools/blender_quality_render.py'
spec=importlib.util.spec_from_file_location('tested_native_quality_renderer',path)
renderer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

class Material(dict):
    def __init__(self,roughness=0.0,metallic=2/3,linked_rough=False,linked_metal=False):
        super().__init__()
        self.name='SourceFacade'
        self.use_nodes=True
        self.node_tree=NS(nodes=[NS(type='BSDF_PRINCIPLED',name='Principled',inputs={
            'Roughness':NS(default_value=roughness,is_linked=linked_rough),
            'Metallic':NS(default_value=metallic,is_linked=linked_metal)})])
    def __bool__(self): return True  # Blender ID objects are truthy even without custom properties.
    def as_pointer(self): return id(self)
    def values_now(self):
        return tuple(self.node_tree.nodes[0].inputs[k].default_value for k in ('Roughness','Metallic'))

def plan(n=300,fps=30):
    return {'fps':fps,'frames':[{'frame':i+1,'time_s':i/fps} for i in range(n)]}

@pytest.mark.parametrize('r,m',[(0,2/3),(.05,1),(.9,0),(.03,.1)])
def test_source_only_preserves_both_inputs(r,m):
    material=Material(r,m)
    before=material.values_now()
    assert renderer.apply_building_finish(material,source_only=True)==[]
    assert material.values_now()==before
    assert dict(material)=={}

def test_enriched_mode_records_both_edits():
    material=Material()
    changes=renderer.apply_building_finish(material,source_only=False)
    assert material.values_now()==(.75,0)
    assert len(changes)==1
    assert changes[0]['old_metallic']==pytest.approx(2/3)
    assert changes[0]['new_metallic']==0
    assert changes[0]['old_roughness']==0 and changes[0]['new_roughness']==.75

def test_metal_only_change_is_still_reported():
    material=Material(.9,.7)
    changes=renderer.apply_building_finish(material,source_only=False)
    assert material.values_now()==(.9,0)
    assert len(changes)==1 and 'old_roughness' not in changes[0]

def test_zero_change_is_not_reported_as_a_change():
    assert renderer.apply_building_finish(Material(.9,0),source_only=False)==[]

@pytest.mark.parametrize('lr,lm',[(True,True),(True,False),(False,True)])
def test_linked_inputs_remain_linked_and_unchanged(lr,lm):
    material=Material(.03,.7,lr,lm)
    renderer.apply_building_finish(material,source_only=False)
    assert material.values_now()==(.03 if lr else .75,.7 if lm else 0)

def test_idempotence():
    material=Material()
    renderer.apply_building_finish(material,source_only=False)
    assert renderer.apply_building_finish(material,source_only=False)==[]

def test_shader_without_principled_is_not_changed():
    material=Material(); material.node_tree.nodes[0].type='EMISSION'
    assert renderer.apply_building_finish(material,source_only=False)==[]
    assert material.values_now()==(0,2/3)

@pytest.mark.parametrize('empty',[None,False])
def test_non_node_material_and_none(empty):
    material=None if empty is None else Material()
    if material is not None: material.use_nodes=False
    assert renderer.apply_building_finish(material,source_only=False)==[]

@pytest.mark.parametrize('paving',[True,False])
def test_source_colour_metadata_matches_paving_choice(paving):
    material=Material()
    renderer.record_surface_appearance(material,paving_look=paving)
    assert material['generic_microdetail'] is True
    assert material['source_base_color_preserved'] is (not paving)
    assert material['source_ortho_colour_preserved'] is (not paving)
    if paving: assert 'not surveyed' in material['appearance_override']

def test_shared_material_is_only_configured_once():
    material=Material(); other=Material(); seen=set()
    assert renderer.new_material(material,seen)
    assert not renderer.new_material(material,seen)
    assert renderer.new_material(other,seen)
    assert len(seen)==2

@pytest.mark.parametrize('n,expected',[(1,[1]),(2,[1,2]),(3,[1,3]),(4,[1,2,4]),(300,[1,150,300])])
def test_stills_are_unique_and_in_range(n,expected):
    assert renderer.select_output_frames(plan(n),animation=False)==expected

@pytest.mark.parametrize('n',[1,2,300])
def test_animation_counts_actual_frames(n):
    assert renderer.select_output_frames(plan(n),animation=True)==list(range(1,n+1))

@pytest.mark.parametrize('damage',['empty','gap','duplicate','bool_id','time','nan','bool_time','bad_fps','bool_fps','float_fps'])
def test_invalid_native_clocks_fail_before_rendering(damage):
    value=plan(3)
    if damage=='empty': value['frames']=[]
    elif damage=='gap': value['frames'][1]['frame']=7
    elif damage=='duplicate': value['frames'][1]['frame']=1
    elif damage=='bool_id': value['frames'][0]['frame']=True
    elif damage=='time': value['frames'][1]['time_s']=.4
    elif damage=='nan': value['frames'][1]['time_s']=math.nan
    elif damage=='bool_time': value['frames'][0]['time_s']=False
    elif damage=='bad_fps': value['fps']=0
    elif damage=='bool_fps': value['fps']=True
    else: value['fps']=30.
    with pytest.raises(ValueError): renderer.select_output_frames(value,animation=True)


def test_main_calls_finish_policy_with_source_only_flag():
    import ast
    tree=ast.parse(path.read_text(encoding='utf8'))
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    calls=[n for n in ast.walk(main) if isinstance(n,ast.Call) and
           isinstance(n.func,ast.Name) and n.func.id=="apply_building_finish"]
    assert len(calls)==1
    source=next(k.value for k in calls[0].keywords if k.arg=="source_only")
    assert isinstance(source,ast.Attribute) and source.attr=="source_only"
    assert isinstance(source.value,ast.Name) and source.value.id=="args"


def test_main_reports_actual_selected_frames_not_constant_three():
    import ast
    tree=ast.parse(path.read_text(encoding='utf8'))
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    pairs=[(k,v) for n in ast.walk(main) if isinstance(n,ast.Dict)
           for k,v in zip(n.keys,n.values) if isinstance(k,ast.Constant)]
    values={k.value:v for k,v in pairs if isinstance(k.value,str)}
    node=values["frames_rendered"]
    assert isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="len"
    assert isinstance(node.args[0],ast.Name) and node.args[0].id=="output_frames"
    assert isinstance(values["rendered_frame_ids"],ast.Name)
    assert values["rendered_frame_ids"].id=="output_frames"


def test_main_sets_colour_metadata_through_policy():
    import ast
    tree=ast.parse(path.read_text(encoding='utf8'))
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    calls=[n for n in ast.walk(main) if isinstance(n,ast.Call) and
           isinstance(n.func,ast.Name) and n.func.id=="record_surface_appearance"]
    assert len(calls)==1
    choice=next(k.value for k in calls[0].keywords if k.arg=="paving_look")
    assert isinstance(choice,ast.Attribute) and choice.attr=="paving_look"
