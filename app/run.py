"""Uruchomienie: python -m app.run (tylko lokalny port)."""
from pathlib import Path
import argparse
import os
import sys

runtime=Path(__file__).resolve().parents[1]/'.runtime/python'
if runtime.is_dir(): sys.path.insert(0,str(runtime))
import uvicorn
from .server import create_app

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data-dir',type=Path,default=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'CentrumKariery'); parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Nieprawidłowy port.')
    print(f'Centrum Kariery: http://127.0.0.1:{args.port}/\nTrwale dane: {args.data_dir}',flush=True)
    uvicorn.run(create_app(args.data_dir,args.port),host='127.0.0.1',port=args.port,proxy_headers=False,access_log=False,log_level='warning',reload=False)
