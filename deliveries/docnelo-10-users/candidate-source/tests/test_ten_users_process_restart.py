"""A genuinely new Python/API process, sharing only synthetic PostgreSQL state."""
import json
import subprocess
import sys

from sqlalchemy import select

from backend.auth import User
from backend.models import now
from tests.test_ten_users_preparation import ten, enroll_ten
from tests.test_public_beta import beta


def test_new_python_api_process_keeps_ten_and_login_after_closure(ten):
    (client, app, sent), clock = ten
    enroll_ten(ten, 10)
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.email == 'synthetic-0@example.test'))
        user.email_verified_at = now()
        db.commit()
    settings = app.state.settings.model_copy(update={'registration_mode':'disabled'})
    program = '''
import json,sys
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app
from backend.account_models import PublicRegistrationQuota
from tests.conftest import BFF_KEY
from tests.test_public_beta import PASSWORD
values=json.load(sys.stdin)
# SecretStr JSON is intentionally masked; re-inject only the public synthetic fixture key.
values['bff_service_key']=BFF_KEY
settings=Settings(_env_file=None,**values)
app=create_app(settings)
with TestClient(app) as client:
    client.headers.update({'X-API-Key':BFF_KEY,'X-Documind-Secure':'1'})
    options=client.get('/api/v1/auth/options').json()
    result=client.post('/api/v1/auth/login',json={'email':'synthetic-0@example.test','password':PASSWORD})
    with app.state.sessions() as db:
        count=db.get(PublicRegistrationQuota,'public').issued_count
    print(json.dumps({'restart_proof':True,'issued_count':count,'login_status':result.status_code,'availability':options['public_registration_availability']}))
app.state.authentication_engine.dispose()
app.state.engine.dispose()
'''
    child = subprocess.run([sys.executable, '-B', '-c', program],
        input=settings.model_dump_json(), capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    evidence = [json.loads(line) for line in child.stdout.splitlines() if '"restart_proof"' in line]
    assert evidence == [{'restart_proof':True, 'issued_count':10, 'login_status':200, 'availability':'closed'}]
