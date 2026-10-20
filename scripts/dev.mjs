import {readFileSync,existsSync} from 'node:fs';
const hint=new URL('./.python-path',import.meta.url);
const python=process.env.LEDGER_PYTHON || (existsSync(hint)?readFileSync(hint,'utf8').trim():'python3');
import {spawn} from 'node:child_process';
const api=spawn(python,['-m','uvicorn','main:app','--host','0.0.0.0','--port','8000'],{cwd:new URL('../backend',import.meta.url),stdio:'inherit'});
const web=spawn('npm',['run','dev','--','--port','4173'],{cwd:new URL('../frontend',import.meta.url),stdio:'inherit'});
function close(){api.kill();web.kill();}
process.on('SIGTERM',close);process.on('SIGINT',close);
api.on('exit',code=>{if(code)web.kill();});web.on('exit',()=>api.kill());
