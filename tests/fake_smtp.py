"""Test-only SMTP/TLS capture, loopback by default. No delivery, relay or credential logging."""
import queue
import shutil
import socketserver
import ssl
import subprocess
import threading
from pathlib import Path

import pytest


@pytest.fixture
def mail_certificate(tmp_path):
    executable = shutil.which('openssl')
    if not executable:
        candidate = Path('C:/Program Files/Git/usr/bin/openssl.exe')
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        pytest.skip('OpenSSL CLI required to generate an ephemeral loopback TLS certificate')
    key, cert = tmp_path / 'loopback.key', tmp_path / 'loopback.crt'
    subprocess.run([executable, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                   check=True, capture_output=True, timeout=20)
    return cert, key


class FakeSMTP:
    def __init__(self, certificate, *, starttls=False, reject=False, host='127.0.0.1', port=0):
        cert, key = certificate
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.messages = queue.Queue()
        self.commands = []
        self.tls_connections = 0
        self.failed = threading.Event()
        self.reject = reject
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                connection = self.request
                connection.settimeout(5)
                secure = False
                try:
                    if not starttls:
                        connection = context.wrap_socket(connection, server_side=True)
                        secure = True
                        owner.tls_connections += 1
                    stream = connection.makefile('rb')
                    def send(line):
                        connection.sendall(line + b'\r\n')
                    send(b'220 loopback.invalid SMTP test')
                    while True:
                        line = stream.readline(8192)
                        if not line:
                            break
                        command = line.split(b' ', 1)[0].strip().upper()
                        owner.commands.append(command)  # Never keep AUTH payloads or addresses.
                        if command in (b'EHLO', b'HELO'):
                            send(b'250-loopback.invalid')
                            send(b'250 AUTH PLAIN' if secure else b'250 STARTTLS')
                        elif command == b'STARTTLS' and not secure:
                            send(b'220 Begin TLS')
                            stream.close()
                            connection = context.wrap_socket(connection, server_side=True)
                            secure = True
                            owner.tls_connections += 1
                            stream = connection.makefile('rb')
                        elif not secure:
                            send(b'530 TLS required')
                        elif command == b'AUTH':
                            send(b'235 Authentication successful')
                        elif command in (b'MAIL', b'RCPT', b'RSET', b'NOOP'):
                            send(b'250 OK')
                        elif command == b'DATA':
                            if owner.reject:
                                send(b'451 Fictitious temporary delivery failure')
                                owner.failed.set()
                                continue
                            send(b'354 End with dot')
                            content = bytearray()
                            while True:
                                part = stream.readline(8192)
                                if not part or len(content) > 65536:
                                    raise ValueError('Invalid test message')
                                if part == b'.\r\n':
                                    break
                                content.extend(part[1:] if part.startswith(b'..') else part)
                            owner.messages.put(bytes(content))
                            send(b'250 Captured locally')
                        elif command == b'QUIT':
                            send(b'221 Bye')
                            break
                        else:
                            send(b'500 Unsupported')
                    stream.close()
                except (OSError, ValueError):
                    owner.failed.set()
                finally:
                    connection.close()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
        self.server = Server((host, port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(6)
        assert not self.thread.is_alive()
