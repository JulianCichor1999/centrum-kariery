"""Uruchom serwer bez dziedziczenia konsoli i uchwytów skryptu startowego."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

def launch(root, runtime, port=8766, directory=None):
    runtime.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'app.run', '--port', str(port)]
    if directory is not None: command.extend(['--data-dir', str(directory)])
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP |
             subprocess.CREATE_BREAKAWAY_FROM_JOB) if os.name == 'nt' else 0
    with (runtime / 'start.stdout.log').open('ab') as output, (runtime / 'start.stderr.log').open('ab') as errors:
        child = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=errors, close_fds=True,
                                 creationflags=flags, start_new_session=os.name != 'nt')
    return child.pid

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--runtime', type=Path, default=root / '.runtime')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Nieprawidłowy port.')
    print(launch(root, args.runtime, args.port, args.data_dir), flush=True)
