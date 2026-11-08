"""Opt-in foreground TCP relay: 127.0.0.1 -> local Docker exec -> internal TLS.

No external Docker network, certificate exception, cleartext HTTP or host bind
inside a container. Stop with Ctrl+C. Requires local Docker access.
"""
import json
from pathlib import Path
import socket
import socketserver
import subprocess
import threading

LAB=Path(__file__).resolve().parent
project=json.loads((LAB/'lab.json').read_text())['project']
assert project.startswith('docnelo-signup-lab-')
BRIDGE='''
import socket,sys,threading
s=socket.create_connection(('proxy',8443),timeout=10)
s.settimeout(None)
def upload():
 try:
  while True:
   data=sys.stdin.buffer.read1(65536)
   if not data:break
   s.sendall(data)
 except OSError:pass
 finally:
  try:s.shutdown(socket.SHUT_WR)
  except OSError:pass
threading.Thread(target=upload,daemon=True).start()
try:
 while True:
  data=s.recv(65536)
  if not data:break
  sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
finally:s.close()
'''
COMMAND=['docker','--host','npipe:////./pipe/docker_engine','compose',
    '--env-file',str(LAB/'empty.env'),'-p',project,'-f',str(LAB/'compose.json'),
    'exec','-T','legal','python','-u','-c',BRIDGE]

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        process=subprocess.Popen(COMMAND,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.request.settimeout(60)
        def upload():
            try:
                while True:
                    data=self.request.recv(65536)
                    if not data:break
                    process.stdin.write(data);process.stdin.flush()
            except (OSError,ValueError):pass
            finally:
                try:process.stdin.close()
                except OSError:pass
        threading.Thread(target=upload,daemon=True).start()
        try:
            while True:
                data=process.stdout.read1(65536)
                if not data:break
                self.request.sendall(data)
        except OSError:pass
        finally:
            process.terminate();process.wait(timeout=10)

class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True
    allow_reuse_address=False

if __name__=='__main__':
    with Server(('127.0.0.1',19446),Handler) as server:
        print('Laboratory relay: https://localhost:19446, bound to 127.0.0.1 (Ctrl+C to stop)',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
