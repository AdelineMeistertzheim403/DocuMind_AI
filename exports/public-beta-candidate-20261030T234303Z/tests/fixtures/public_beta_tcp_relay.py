"""TEST ONLY: transparent TLS relay to give Traefik a distinct real peer per test entry."""
import os
import socket
import socketserver
import threading

assert os.environ.get('DOCUMIND_TEST_ONLY')=='sprint-14-6'
port=int(os.environ['RELAY_TARGET_PORT'])
assert port in (8443,8444,8445)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(('traefik',port),timeout=5) as upstream:
            self.request.settimeout(30);upstream.settimeout(30)
            def copy(source,target):
                try:
                    while data:=source.recv(65536):target.sendall(data)
                except OSError:pass
                finally:
                    for connection in (source,target):
                        try:connection.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
            thread=threading.Thread(target=copy,args=(self.request,upstream),daemon=True)
            thread.start();copy(upstream,self.request);thread.join(6)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True


with Server(('0.0.0.0',8443),Handler) as server:server.serve_forever()
