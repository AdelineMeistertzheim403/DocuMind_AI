"""Generate an isolated Compose project, using only new synthetic configuration."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import textwrap
from uuid import uuid4

LAB=Path(__file__).resolve().parent
ROOT=LAB.parents[1]
project='docnelo-signup-lab-'+uuid4().hex[:10]
assert not (LAB/'compose.json').exists(), 'Refuse to replace an existing lab'
(LAB/'tls').mkdir()
openssl=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','2',
    '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,DNS:smtp,IP:127.0.0.1',
    '-out',str(LAB/'tls/lab.crt'),'-keyout',str(LAB/'tls/lab.key')],check=True,capture_output=True)
(LAB/'empty.env').write_text('',encoding='utf-8')
(LAB/'recovery.json').write_text('{"format":1,"state":"ready"}\n',encoding='utf-8')
fixtures=LAB/'fixtures/tests'; fixtures.mkdir(parents=True)
(fixtures/'__init__.py').write_text('',encoding='utf-8')
for file in ('fake_smtp.py','fixtures/public_beta_smtp.py'):
    dest=fixtures/file; dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(LAB/'source/tests'/file,dest)
(fixtures/'fixtures/__init__.py').write_text('',encoding='utf-8')
legal=LAB/'legal'; legal.mkdir()
for page in ('terms','privacy','notice'):
    (legal/page).write_text('LABORATOIRE JETABLE — TEXTE SYNTHÉTIQUE NON CONTRACTUEL\n'
        'Version lab-only-v1. Aucune inscription publique réelle ni approbation juridique.\n',encoding='utf-8')
api='sha256:4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d'
web='sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362'
db='sha256:d2e0a72a9da278610fc926cc8d125827c0069f33feaafa011aae890572ec95c3'
proofs='sha256:526917bd27ecc837a7b683c0ca396fcdf315dde81c879100bffda874a3abeb1d'
# Resolve this installed auxiliary image once; all Compose services are immutable IDs.
docker=['docker','--host','npipe:////./pipe/docker_engine']
proxy=subprocess.check_output(docker+['image','inspect','traefik:v3.3','--format','{{.Id}}'],text=True).strip()
assert proxy=='sha256:ff8877338069e690053302ba9a8d8eeb47259467774ea90826f77a32e787a488', 'Auxiliary proxy image changed; review provenance'
key=secrets.token_hex(32); gateway=secrets.token_hex(32)
env=dict(DATABASE_URL='postgresql+psycopg://synthetic:lab-only-password@db:5432/synthetic',
    BFF_SERVICE_KEY=key,REGISTRATION_MODE='public',APPLICATION_PROFILE='standard',
    PUBLIC_REGISTRATION_LIMIT='5',PUBLIC_REGISTRATION_PER_HOUR='10',
    PUBLIC_LEGAL_READY='true',PUBLIC_OPERATOR_NAME='Synthetic laboratory operator',
    PUBLIC_CONTACT_EMAIL='operator@example.test',PUBLIC_TERMS_VERSION='lab-only-v1',
    PUBLIC_TERMS_URL='https://localhost:19446/lab-legal/terms',
    PUBLIC_PRIVACY_URL='https://localhost:19446/lab-legal/privacy',
    PUBLIC_LEGAL_NOTICE_URL='https://localhost:19446/lab-legal/notice',
    ACCOUNT_BASE_URL='https://localhost:19446',SMTP_HOST='smtp',SMTP_PORT='8025',
    SMTP_STARTTLS='true',SMTP_FROM='sender@example.test',SMTP_USERNAME='',SMTP_PASSWORD='',
    SSL_CERT_FILE='/certs/lab.crt',AI_ENABLED='false',OWNER_DEMO_ENABLED='false',
    LEGACY_API_ENABLED='false',API_KEYS='{}',LIFECYCLE_DURABLE_RECEIPTS_REQUIRED='true',
    LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED='false',STORAGE_DIR='/app/var/documents',
    EXTRACTION_MODE='sandbox',RECOVERY_STATE_PATH='/control/recovery.json',
    LIFECYCLE_DATA_ROOT='/app/lifecycle',LIFECYCLE_BACKUP_LOCK_PATH='/app/lifecycle/.backup.lock',
    LIFECYCLE_AUTHENTICATED_NAMESPACE=project,
    LIFECYCLE_AUTHENTICATION_KEY_PATH='/app/lifecycle/keys/authentication.key',
    LIFECYCLE_ADMISSION_KEY_PATH='/app/lifecycle/keys/admission.key',PYTHONDONTWRITEBYTECODE='1')
for variable,path in dict(REGISTRY='registry/registry.sqlite',CONFIRMATION='confirmation/confirmation.sqlite',
    AUTHENTICATED_CONFIRMATION='authenticated/authenticated.sqlite',HOLDS='holds/holds.sqlite',
    ADMISSION_ANCHOR='admissions/admissions.sqlite').items():
    env['LIFECYCLE_'+variable+'_PATH']='/app/lifecycle/'+path
# Reuse only the reviewed two-phase init program, never the VPS Compose configuration.
vps=(ROOT/'compose.public-beta.vps.yaml').read_text(encoding='utf-8')
init=textwrap.dedent(vps.split('      - |\n',1)[1].split('\n  api:',1)[0]).strip()+'\n'
(LAB/'lifecycle_init.py').write_text(init,encoding='utf-8')
def service(image):
    return dict(image=image,pull_policy='never',networks=['isolated'],read_only=True,
        cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
        labels={'docnelo.lab':project,'traefik.enable':'false'},pids_limit=128,
        mem_limit='512m',tmpfs=['/tmp:size=64m,mode=1777'])
services={}
services['db']=dict(service(db),user='70:70',mem_limit='1g',
    tmpfs=['/tmp:size=64m,mode=1777','/var/run/postgresql:uid=70,gid=70,mode=0700'],
    environment=dict(POSTGRES_USER='synthetic',POSTGRES_PASSWORD='lab-only-password',POSTGRES_DB='synthetic'),
    volumes=['database:/var/lib/postgresql/data'],
    healthcheck=dict(test=['CMD','pg_isready','-U','synthetic','-d','synthetic'],interval='2s',retries=30))
base=dict(service(api),environment=env,mem_limit='1536m',
    volumes=['documents:/app/var','lifecycle:/app/lifecycle','./tls:/certs:ro','./recovery.json:/control/recovery.json:ro'])
services['api']=dict(base,command=['uvicorn','backend.main:app','--host','0.0.0.0','--port','8000','--workers','1','--no-access-log'],
    depends_on={'db':{'condition':'service_healthy'}},
    healthcheck=dict(test=['CMD','python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3)"],interval='3s',retries=30))
services['lifecycle-init']=dict(base,user='0:0',entrypoint=['python'],command=['/lab/lifecycle_init.py'],
    cap_add=['CHOWN','FOWNER','DAC_OVERRIDE','SETUID','SETGID'],
    volumes=base['volumes']+['./lifecycle_init.py:/lab/lifecycle_init.py:ro'],profiles=['tools'])
services['migrate']=dict(base,entrypoint=['alembic'],command=['upgrade','head'],profiles=['tools'],
    depends_on={'db':{'condition':'service_healthy'}})
services['web']=dict(service(web),environment=dict(BFF_SERVICE_KEY=key,BFF_BACKEND_URL='http://api:8000',
    BFF_HOST='0.0.0.0',BFF_PORT='3000',BFF_ALLOWED_HOSTS='localhost,127.0.0.1',
    DOCUMIND_GATEWAY_TOKEN=gateway,BFF_TRUSTED_PROXY_IPS=''))
services['smtp']=dict(service(proofs),user='0:0',working_dir='/fixture',
    environment=dict(DOCUMIND_TEST_ONLY='sprint-14-6',PYTHONPATH='/fixture',PYTHONDONTWRITEBYTECODE='1'),
    entrypoint=['python'],command=['-m','tests.fixtures.public_beta_smtp'],
    volumes=['./fixtures:/fixture:ro','./tls/lab.crt:/certs/recipe.crt:ro',
        './tls/lab.key:/certs/recipe.key:ro','capture:/capture'])
services['legal']=dict(service(api),entrypoint=['python'],command=['-m','http.server','8080','--directory','/legal'],
    volumes=['./legal:/legal:ro'])
dynamic={'http':{'routers':{'lab':{'entryPoints':['lab'],'rule':'Host(`localhost`) || Host(`127.0.0.1`)',
    'service':'web','tls':{},'middlewares':['gateway']},
    'legal':{'entryPoints':['lab'],'rule':'PathPrefix(`/lab-legal/`)','priority':100,
    'service':'legal','tls':{},'middlewares':['strip']}},
    'services':{'web':{'loadBalancer':{'servers':[{'url':'http://web:3000'}]}},
    'legal':{'loadBalancer':{'servers':[{'url':'http://legal:8080'}]}}},
    'middlewares':{'gateway':{'headers':{'customRequestHeaders':{'X-Documind-Gateway':gateway,'X-Forwarded-Proto':'https'}}},
    'strip':{'stripPrefix':{'prefixes':['/lab-legal']}}}},
    'tls':{'certificates':[{'certFile':'/certs/lab.crt','keyFile':'/certs/lab.key'}]}}
(LAB/'proxy.json').write_text(json.dumps(dynamic,indent=2),encoding='utf-8')
services['proxy']=dict(service(proxy),user='1000:1000',command=['--entrypoints.lab.address=:8443',
    '--providers.file.filename=/config/proxy.json','--api=false'],
    volumes=['./proxy.json:/config/proxy.json:ro','./tls:/certs:ro'])
compose=dict(name=project,services=services,networks={'isolated':{'internal':True,'labels':{'docnelo.lab':project}}},
    volumes={name:{'labels':{'docnelo.lab':project}} for name in ['database','documents','lifecycle','capture']})
(LAB/'compose.json').write_text(json.dumps(compose,indent=2),encoding='utf-8')
(LAB/'lab.json').write_text(json.dumps(dict(project=project,web=web,api=api,postgres=db,
    proofs=proofs,proxy=proxy,origin='https://localhost:19446',verdict='NOT_RUN'),indent=2),encoding='utf-8')
print(project)
