"""Single-authority collaboration service. Run ONE worker; see docs for scaling."""
import asyncio, os, uuid
from datetime import datetime, timezone
from decimal import InvalidOperation
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Integer, Text, select
from sqlalchemy.orm import declarative_base, Session
import jwt
from engine import Engine, FormulaError
from seed import seed

DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./ledger.db')
AUTH_DOMAIN=os.getenv('AUTH0_DOMAIN',''); AUDIENCE=os.getenv('AUTH0_AUDIENCE','')
DEMO=os.getenv('DEMO_MODE','true').lower()=='true'
db=create_engine(DATABASE_URL,connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {})
Base=declarative_base()
class Cell(Base):
    __tablename__='cells'
    address=Column(String(16),primary_key=True); raw=Column(Text,nullable=False); revision=Column(Integer,default=0)
class Event(Base):
    __tablename__='events'
    id=Column(Integer,primary_key=True,autoincrement=True); cell=Column(String(16)); before=Column(Text); after=Column(Text); actor=Column(String(200)); timestamp=Column(String(40)); revision=Column(Integer)
Base.metadata.create_all(db)
with Session(db) as s:
    stored=s.scalars(select(Cell)).all()
    if not stored:
        for c,r in seed().items(): s.add(Cell(address=c,raw=r,revision=0))
        s.commit(); stored=s.scalars(select(Cell)).all()
    engine=Engine({c.address:c.raw for c in stored}); revisions={c.address:c.revision for c in stored}
    sequence=max((e for e in s.scalars(select(Event.id)).all()),default=0)
app=FastAPI(title='Ledger',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173,http://localhost:8080').split(','),allow_methods=['GET'],allow_headers=['*'])
lock=asyncio.Lock(); clients={}
jwks=jwt.PyJWKClient(f'https://{AUTH_DOMAIN}/.well-known/jwks.json') if AUTH_DOMAIN else None

def identity(token):
    if DEMO: return 'demo:'+uuid.uuid4().hex[:6]
    if not jwks or not AUDIENCE: raise ValueError('Auth0 not configured')
    key=jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(token,key,algorithms=['RS256'],audience=AUDIENCE,issuer=f'https://{AUTH_DOMAIN}/')['sub']

def snapshot(): return {'type':'snapshot','cells':engine.snapshot(),'revisions':revisions,'sequence':sequence,'demo':DEMO}
async def broadcast(message):
    # Bounded send: one slow consumer cannot hold the authority lock indefinitely.
    async def send(ws):
        try: await asyncio.wait_for(ws.send_json(message),2)
        except Exception: clients.pop(ws,None)
    await asyncio.gather(*(send(ws) for ws in list(clients)))

@app.get('/health')
def health(): return {'status':'ok','mode':'demo' if DEMO else 'auth0','authority':'single-worker'}
@app.get('/api/history/{address}')
def history(address:str):
    if not DEMO: raise HTTPException(403,'History is delivered through the authenticated WebSocket')
    return get_history(address)
def get_history(address):
    with Session(db) as s:
        events=s.scalars(select(Event).where(Event.cell==address.upper()).order_by(Event.id.desc()).limit(30)).all()
        return [{'id':e.id,'before':e.before,'after':e.after,'actor':e.actor,'timestamp':e.timestamp} for e in events]

@app.websocket('/ws')
async def websocket(ws:WebSocket):
    global sequence,engine
    await ws.accept()
    try:
        hello=await asyncio.wait_for(ws.receive_json(),10)
        actor=await asyncio.to_thread(identity,hello.get('token',''))
    except Exception:
        await ws.close(code=1008); return
    async with lock:
        clients[ws]=actor; await ws.send_json({**snapshot(),'actor':actor})
        await broadcast({'type':'presence','count':len(clients)})
    try:
        while True:
            message=await ws.receive_json()
            if not isinstance(message,dict):
                await ws.send_json({'type':'error','message':'Expected a JSON object'}); continue
            async with lock:
                if message.get('type')=='history':
                    await ws.send_json({'type':'history','cell':message.get('cell'),'events':get_history(str(message.get('cell','')))})
                    continue
                if message.get('type')!='edit': continue
                cell=str(message.get('cell','')).upper(); raw=str(message.get('raw','')); op=str(message.get('op',''))[:100]
                if cell not in engine.raw:
                    await ws.send_json({'type':'error','message':'Choose an existing model cell','op':op}); continue
                current=revisions.get(cell,0)
                if message.get('base_revision')!=current:
                    await ws.send_json({'type':'conflict','cell':cell,'op':op,'message':'Another edit was committed first. Review the current value before retrying.',**snapshot() ,'type':'conflict'}); continue
                before=engine.raw[cell]
                try:
                    stats=engine.set(cell,raw)
                    with Session(db) as s:
                        row=s.get(Cell,cell); row.raw=raw; row.revision=current+1
                        event=Event(cell=cell,before=before,after=raw,actor=actor,timestamp=datetime.now(timezone.utc).isoformat(),revision=current+1)
                        s.add(event); s.commit(); sequence=event.id
                    revisions[cell]=current+1
                except (FormulaError,InvalidOperation,ValueError) as exc:
                    await ws.send_json({'type':'error','message':str(exc),'op':op}); continue
                except Exception:
                    # Reload durable state following a failed transaction.
                    with Session(db) as s: engine=Engine({c.address:c.raw for c in s.scalars(select(Cell)).all()})
                    await ws.send_json({'type':'error','message':'Persistence failed; edit rolled back','op':op}); continue
                current_snapshot=engine.snapshot()
                await broadcast({'type':'commit','op':op,'cell':cell,'actor':actor,'sequence':sequence,'revision':current+1,'patch':{c:current_snapshot[c] for c in stats['affected']},'stats':stats})
    except (WebSocketDisconnect,RuntimeError): pass
    finally:
        async with lock:
            clients.pop(ws,None); await broadcast({'type':'presence','count':len(clients)})
