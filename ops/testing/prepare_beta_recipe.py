"""Generate ONLY new, fictitious local recipe artifacts. Does not run Docker or deploy."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('name',help='New s14-6-recipe-<hex> directory under ignored var/')
    args=parser.parse_args()
    if not re.fullmatch(r's14-6-recipe-[a-f0-9]{4,12}',args.name):raise SystemExit('Invalid local recipe name')
    root=Path(__file__).resolve().parents[2]
    directory=root/'var'/args.name
    directory.mkdir(mode=0o700)  # Refuse any existing directory; never overwrite test or private files.
    tls=directory/'tls';tls.mkdir(mode=0o700)
    (directory/'capture').mkdir(mode=0o700)
    executable=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
    cert,key=tls/'recipe.crt',tls/'recipe.key'
    subprocess.run([executable,'req','-x509','-newkey','rsa:2048','-nodes','-days','2',
        '-subj','/CN=documind.test','-addext','subjectAltName=DNS:documind.test,DNS:localhost,DNS:smtp,IP:127.0.0.1',
        '-out',str(cert),'-keyout',str(key)],check=True,capture_output=True,timeout=20)
    key.chmod(0o600)
    public=subprocess.run([executable,'x509','-in',str(cert),'-pubkey','-noout'],capture_output=True,check=True).stdout
    der=subprocess.run([executable,'pkey','-pubin','-outform','DER'],input=public,capture_output=True,check=True).stdout
    env=directory/'fictitious.env'
    values={'BETA_RECIPE_DIR':directory.as_posix(),'BETA_RECIPE_ENV':env.as_posix(),
        'BFF_SERVICE_KEY':'fictitious-s14-6-service-key-no-real-secret-0001',
        'REGISTRATION_MODE':'public','PUBLIC_REGISTRATION_LIMIT':'5','AI_ENABLED':'false',
        'OWNER_DEMO_ENABLED':'false','LEGACY_API_ENABLED':'false','API_KEYS':'{}',
        'PUBLIC_LEGAL_READY':'true','PUBLIC_OPERATOR_NAME':'Fictitious recipe operator',
        'PUBLIC_CONTACT_EMAIL':'contact@example.test','PUBLIC_TERMS_VERSION':'beta-test-v1',
        'PUBLIC_LEGAL_NOTICE_URL':'https://documind.test/legal-notice',
        'PUBLIC_PRIVACY_URL':'https://documind.test/privacy','PUBLIC_TERMS_URL':'https://documind.test/terms',
        'ACCOUNT_BASE_URL':'https://documind.test:19443','SMTP_HOST':'smtp','SMTP_PORT':'8025',
        'SMTP_STARTTLS':'true','SMTP_FROM':'sender@example.test','SMTP_USERNAME':'fictitious-user',
        'SMTP_PASSWORD':'fictitious-password'}
    env.write_text(''.join(f'{name}={value}\n' for name,value in values.items()),encoding='utf-8')
    env.chmod(0o600)
    project='documind-'+args.name
    record={'project':project,'directory':str(directory),'certificate':str(cert),
        'spki':base64.b64encode(hashlib.sha256(der).digest()).decode(),
        'compose':['docker','--host','npipe:////./pipe/dockerDesktopLinuxEngine','compose',
            '--env-file',str(env),'-p',project,'-f',str(root/'compose.public-beta-test.yaml')]}
    (directory/'recipe.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    import fitz
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72,72),'Fictitious preproduction document. No personal data. Local analysis only.')
        pdf.save(directory/'fictitious.pdf')
    print('New fictitious recipe prepared:',project)


if __name__=='__main__':main()
