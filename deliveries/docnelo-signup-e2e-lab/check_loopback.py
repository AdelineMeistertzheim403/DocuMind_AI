"""Verify loopback TLS with the lab CA, then stop the temporary relay."""
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import urllib.request

LAB=Path(__file__).resolve().parent
process=subprocess.Popen([sys.executable,str(LAB/'loopback_relay.py')],stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:
    for attempt in range(30):
        try:
            with socket.create_connection(('127.0.0.1',19446),timeout=.2):break
        except OSError:
            assert process.poll() is None,'Relay process exited'
            time.sleep(.2)
    context=ssl.create_default_context(cafile=str(LAB/'tls/lab.crt'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    results=[]
    for path in ['/','/register','/lab-legal/terms','/bff/auth/options']:
        with opener.open('https://localhost:19446'+path,timeout=15) as response:
            data=response.read()
            assert response.status==200
            results.append(dict(path=path,status=response.status))
            if path.endswith('options'):
                assert json.loads(data)['public_registration_availability']=='closed'
    proof=dict(status='PASS',bind='127.0.0.1:19446',tls_certificate_verified=True,
        transport='local Docker exec TCP relay to internal proxy; no external network',
        browser_interaction_performed=False,requests=results)
    (LAB/'loopback-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    print(json.dumps(proof))
finally:
    process.terminate();process.wait(timeout=10)
