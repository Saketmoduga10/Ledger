from fastapi.testclient import TestClient
from main import app

def until(ws, kind):
    for _ in range(20):
        event=ws.receive_json()
        if event['type']==kind:return event
    raise AssertionError('Expected '+kind)

def test_two_clients_converge_conflict_cycle_history_reconnect():
    client=TestClient(app)
    with client.websocket_connect('/ws') as a, client.websocket_connect('/ws') as b:
        a.send_json({'type':'hello'}); sa=until(a,'snapshot')
        b.send_json({'type':'hello'}); sb=until(b,'snapshot')
        rev=sa['revisions']['B3']
        a.send_json({'type':'edit','cell':'B3','raw':'0.11','base_revision':rev,'op':'first'})
        ca=until(a,'commit'); cb=until(b,'commit')
        assert ca['patch']==cb['patch'] and ca['sequence']==cb['sequence']
        b.send_json({'type':'edit','cell':'B3','raw':'0.99','base_revision':rev,'op':'stale'})
        conflict=until(b,'conflict'); assert conflict['cells']['B3']['raw']=='0.11'
        b.send_json({'type':'edit','cell':'B3','raw':'=B3','base_revision':rev+1,'op':'cycle'})
        assert '#CYCLE' in until(b,'error')['message']
        a.send_json({'type':'history','cell':'B3'}); assert until(a,'history')['events'][0]['after']=='0.11'
    with client.websocket_connect('/ws') as c:
        c.send_json({'type':'hello'}); s=until(c,'snapshot'); assert s['cells']['B3']['raw']=='0.11'

def test_auth_fails_closed_when_required_but_unconfigured(monkeypatch):
    import main
    from starlette.websockets import WebSocketDisconnect
    import pytest
    monkeypatch.setattr(main,'DEMO',False)
    monkeypatch.setattr(main,'jwks',None)
    with TestClient(app).websocket_connect('/ws') as ws:
        ws.send_json({'type':'hello','token':'invalid'})
        with pytest.raises(WebSocketDisconnect) as exc:ws.receive_json()
        assert exc.value.code==1008
