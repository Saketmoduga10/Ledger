"""Real WebSocket load test. Start a fresh demo backend before running.
10 clients submit 5,000 overlapping edit ATTEMPTS. Stale edits are rejected.
Measures acknowledged edit round trips; not simultaneous users or pure network latency.
"""
import asyncio,json,statistics,time,sys
import websockets
async def run(url, mode):
    sockets=[await websockets.connect(url,max_size=2**22) for _ in range(10)]
    states=[]; revisions=[]; ready=[]; latencies=[]; committed=0; conflicts=0; seqs=[0]*10
    for ws in sockets:
        await ws.send(json.dumps({'type':'hello'}))
        while True:
            m=json.loads(await ws.recv())
            if m['type']=='snapshot':break
        states.append(m['cells']);revisions.append(m['revisions']);ready.append({})
    async def receive(i):
        nonlocal committed,conflicts
        async for raw in sockets[i]:
            m=json.loads(raw)
            if m['type']=='commit':
                states[i].update(m['patch']);revisions[i][m['cell']]=m['revision'];seqs[i]=m['sequence']
            elif m['type']=='conflict':
                states[i]=m['cells'];revisions[i]=m['revisions'];seqs[i]=m['sequence']
            if m.get('op') in ready[i]:
                future,start=ready[i].pop(m['op']);latencies.append((time.perf_counter()-start)*1000)
                if m['type']=='commit': committed+=1
                elif m['type']=='conflict':conflicts+=1
                else:raise RuntimeError(m)
                future.set_result(True)
    readers=[asyncio.create_task(receive(i)) for i in range(10)]
    async def writer(i):
        for j in range(500):
            cell=['B4','C4','D4','E4','F4','G4','B11','C11','D11','E11'][i] if mode=='disjoint' else 'B4'
            op=f'{i}:{j}';f=asyncio.get_running_loop().create_future();ready[i][op]=(f,time.perf_counter())
            await sockets[i].send(json.dumps({'type':'edit','cell':cell,'raw':str(200+i+j),'base_revision':revisions[i][cell],'op':op}))
            await asyncio.wait_for(f,30)
    await asyncio.gather(*(writer(i) for i in range(10)))
    # Read authoritative snapshots on new connections; existing streams must drain to their final sequence.
    fresh=await websockets.connect(url);await fresh.send(json.dumps({'type':'hello'}))
    final=json.loads(await fresh.recv());await fresh.close()
    deadline=time.monotonic()+15
    while any(s<final['sequence'] for s in seqs):
        if time.monotonic()>deadline:raise TimeoutError('Clients failed to converge')
        await asyncio.sleep(.01)
    divergence=sum(s!=final['cells'] for s in states)
    for ws in sockets:await ws.close()
    await asyncio.gather(*readers,return_exceptions=True)
    result={'workload':mode,'clients':10,'edit_attempts':5000,'committed':committed,'conflicts':conflicts,'divergent_clients':divergence,'median_acknowledgement_ms':round(statistics.median(latencies),2),'p95_acknowledgement_ms':round(sorted(latencies)[int(len(latencies)*.95)],2),'scope':'Localhost; single server worker; revision conflicts count as rejected attempts.'}
    print(json.dumps(result,indent=2));assert divergence==0 and committed+conflicts==5000
asyncio.run(run(sys.argv[1] if len(sys.argv)>1 else 'ws://localhost:8000/ws', sys.argv[2] if len(sys.argv)>2 else 'contention'))
