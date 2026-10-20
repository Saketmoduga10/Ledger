import {defineConfig} from 'vite';
export default defineConfig({server:{host:'0.0.0.0',allowedHosts:['terminal.local'],proxy:{'/ws':{target:'ws://127.0.0.1:8000',ws:true},'/api':{target:'http://127.0.0.1:8000'},'/health':{target:'http://127.0.0.1:8000'}}}});
