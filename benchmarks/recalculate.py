"""Paired workload: sparse edits in 200 independent 30-cell formula chains."""
import sys,json,platform,statistics,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from engine import Engine,column,evaluate
raw={}
for c in range(1,201):
    col=column(c);raw[col+'1']='100'
    for r in range(2,31):raw[col+str(r)]=f'={col}{r-1}*1.01+2'
e=Engine(raw); incremental=[]; full=[]
for i in range(120):
    start=time.perf_counter();e.set('A1',str(100+i));incremental.append((time.perf_counter()-start)*1000)
    start=time.perf_counter()
    for c in raw:e.values[c]=evaluate(e.ast[c],e.values)
    full.append((time.perf_counter()-start)*1000)
result={'python':platform.python_version(),'platform':platform.platform(),'cells':len(raw),'changed_cells':1,'affected_cells':30,'iterations':120,'incremental_median_ms':round(statistics.median(incremental),3),'full_evaluation_median_ms':round(statistics.median(full),3),'scope':'In-process engine; excludes network and database. Full evaluation reuses parsed ASTs.'}
print(json.dumps(result,indent=2))
