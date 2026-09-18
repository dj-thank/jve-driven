"""Contract-only tests. Network responses and CARLA API objects here are test doubles."""
import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
import pytest
from jevdrive import jev
from jevdrive.control import Observation
from jevdrive.carla_bridge import conversion_settings
from jevdrive.world import DEFAULT_PROJ


def obs(): return Observation(1,.05,0,8.33,100)


def service_with_error(monkeypatch,status,retry=None):
    monkeypatch.setattr(jev.time,'monotonic',lambda:100.)
    s=jev.DecisionService(key='test-only-never-sent')
    f=Future();f.set_exception(jev.JevError('test',http_status=status,retry_after_s=retry))
    s.future=f
    assert s.poll(obs()) is None
    return s


@pytest.mark.parametrize('status',[401,403,422])
def test_auth_and_contract_errors_disable_requests(monkeypatch,status):
    s=service_with_error(monkeypatch,status)
    try:
        assert s.disabled and s.calls==0 and s.last_error==f'HTTP_{status}'
        assert s.poll(obs()) is None and s.calls==0
    finally: s.close()


@pytest.mark.parametrize('status',[429,529,503])
def test_transient_errors_back_off_without_immediate_retry(monkeypatch,status):
    s=service_with_error(monkeypatch,status,9)
    try:
        assert not s.disabled and s.next_at==109 and s.calls==0
        assert s.evidence[0]['backoff_s']==9
        assert 'test-only' not in str(s.evidence)
    finally: s.close()


def test_retry_backoff_grows(monkeypatch):
    s=service_with_error(monkeypatch,529)
    try:
        f=Future();f.set_exception(jev.JevError('test',http_status=529));s.future=f
        s.poll(obs())
        assert s.failures==2 and s.next_at==104
    finally:s.close()


@pytest.mark.parametrize('model',['jev-latest','jev-preview','other'])
def test_runtime_requires_exact_pin(model):
    with pytest.raises(ValueError): jev.DecisionService(key='test-only',model=model)


@pytest.mark.parametrize('budget',[True,0,-1,1.5])
def test_invalid_request_budget(budget):
    with pytest.raises(ValueError): jev.DecisionService(key='test-only',max_calls=budget)


def fake_http(monkeypatch,handler):
    import httpx
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(**kw,transport=httpx.MockTransport(handler)))


def test_http_deadline_does_not_wait_for_slow_model(monkeypatch):
    async def handler(request):
        await asyncio.sleep(2)
    fake_http(monkeypatch,handler)
    with pytest.raises(jev.JevError,match='deadline'):
        asyncio.run(jev._request_async(jev.payload(obs()),'test-only',.02))


def test_http_rate_limit_preserves_sanitized_retry_header(monkeypatch):
    import httpx
    fake_http(monkeypatch,lambda request:httpx.Response(429,headers={'retry-after':'15'}))
    with pytest.raises(jev.JevError) as caught:
        asyncio.run(jev._request_async(jev.payload(obs()),'test-only',1))
    assert caught.value.http_status==429 and caught.value.retry_after_s==15


def test_http_rejects_large_reply(monkeypatch):
    import httpx
    fake_http(monkeypatch,lambda request:httpx.Response(200,content=b'x'*1_000_001))
    with pytest.raises(jev.JevError,match='too_large'):
        asyncio.run(jev._request_async(jev.payload(obs()),'test-only',1))


def test_carla_conversion_does_not_invent_signalized_junctions():
    class Settings:
        proj_string='';use_offsets=True;center_map=True;default_lane_width=0
        generate_traffic_lights=False;all_junctions_with_traffic_lights=True
        def set_osm_way_types(self,types):self.types=types
    c=SimpleNamespace(Osm2OdrSettings=Settings,Osm2Odr=object())
    s=conversion_settings(c,DEFAULT_PROJ)
    assert s.proj_string==DEFAULT_PROJ and not s.center_map and not s.use_offsets
    assert s.generate_traffic_lights and not s.all_junctions_with_traffic_lights
    assert 'track' not in s.types


def test_missing_carla_capability_fails_explicitly():
    with pytest.raises(RuntimeError,match='does not provide'):
        conversion_settings(SimpleNamespace(),DEFAULT_PROJ)
