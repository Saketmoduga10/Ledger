"""Run isolated local WebSocket benchmark without modifying the application DB."""
import os,subprocess,sys,tempfile,time,urllib.request,socket
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with socket.socket() as s:
    s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with tempfile.TemporaryDirectory() as tmp:
    env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp}/bench.db','DEMO_MODE':'true'}
    process=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port)],cwd=root/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try: urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1);break
            except Exception:
                if process.poll() is not None: raise RuntimeError('Server failed to start')
                time.sleep(.1)
        result=subprocess.run([sys.executable,str(root/'benchmarks/collaboration.py'),f'ws://127.0.0.1:{port}/ws',sys.argv[1] if len(sys.argv)>1 else 'contention'],capture_output=True,text=True,timeout=180)
        if result.returncode:raise RuntimeError(result.stderr)
        print(result.stdout,end='')
    finally:process.terminate();process.wait()
