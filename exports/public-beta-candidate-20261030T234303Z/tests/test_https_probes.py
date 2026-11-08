import errno
import json
import socket
import ssl
from email.message import Message

import pytest

from tools import deploy_production as deploy


@pytest.fixture
def probes(monkeypatch):
    clock=[0.0];calls=[];answers=[]
    cookie='__Host-documind-csrf=private-cookie; Secure; HttpOnly; SameSite=Strict; Path=/'
    class Response:
        def __init__(self,status,headers):self.status,self.headers=status,headers
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Opener:
        def open(self,url,timeout):
            calls.append((url,timeout))
            answer=answers.pop(0) if answers else (401 if url.endswith('/documents') else 200)
            if isinstance(answer,Exception):raise answer
            status,value=answer if isinstance(answer,tuple) else (answer,cookie)
            headers=Message()
            if value:headers['Set-Cookie']=value
            if status>=300:raise deploy.urllib.error.HTTPError(url,status,'private-response',headers,None)
            return Response(status,headers)
    def build(*handlers):
        https=next(value for value in handlers if isinstance(value,deploy.urllib.request.HTTPSHandler))
        assert https._context.verify_mode==ssl.CERT_REQUIRED and https._context.check_hostname
        redirect=next(value for value in handlers if isinstance(value,deploy.NoProbeRedirect))
        assert redirect.redirect_request(None,None,None,None,None,None) is None
        return Opener()
    monkeypatch.setattr(deploy.urllib.request,'build_opener',build)
    monkeypatch.setattr(deploy.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(deploy.time,'sleep',lambda duration:clock.__setitem__(0,clock[0]+duration))
    return answers,calls,clock


def test_https_checks_every_path_cookie_and_anonymous_401(probes):
    answers,calls,clock=probes;report={}
    deploy.https_check(report)
    assert [url for url,_ in calls]==[f'https://{deploy.HOST}{path}' for path in
        ('/login','/bff/health','/bff/auth/csrf','/bff/documents')]
    assert all(event['result']=='ok' for event in report['https_probes'])
    assert report['https_probes'][-1]['http_status']==401
    assert 'private-cookie' not in json.dumps(report)


@pytest.mark.parametrize('status',[404,502,503,504])
def test_traefik_discovery_is_retried_then_all_checks_run(probes,status):
    answers,calls,clock=probes;answers.extend([status,200,200,200,401]);report={}
    deploy.https_check(report)
    assert clock[0]==2 and len(calls)==5
    assert report['https_probes'][0]['http_status']==status
    assert report['https_probes'][-1]['result']=='ok'


@pytest.mark.parametrize('index',[1,2,3])
def test_transient_failure_on_later_path_restarts_the_whole_sequence(probes,index):
    answers,calls,clock=probes;answers.extend([200]*index+[503]);report={}
    deploy.https_check(report)
    assert len(calls)==index+5 and clock[0]==2
    assert calls[index+1][0].endswith('/login')
    assert report['https_probes'][-1]['http_status']==401


def test_retry_deadline_is_bounded_and_identifies_last_url(probes):
    answers,calls,clock=probes;answers.extend([404]*10);report={}
    with pytest.raises(deploy.HTTPSProbeError):deploy.https_check(report,timeout_seconds=3,interval_seconds=2)
    assert clock[0]==3 and len(calls)==2
    assert calls[0][1]==3 and calls[1][1]==1
    assert report['https_probes'][-1]['cause']=='deadline_exceeded'
    assert all(event['url']==f'https://{deploy.HOST}/login' for event in report['https_probes'])


@pytest.mark.parametrize('status',[301,302,400,401,403,500])
def test_permanent_http_failures_do_not_wait_or_follow_redirects(probes,status):
    answers,calls,clock=probes;answers.append(status);report={}
    with pytest.raises(deploy.HTTPSProbeError):deploy.https_check(report)
    assert len(calls)==1 and clock[0]==0
    assert report['https_probes'][0]['http_status']==status


@pytest.mark.parametrize('cookie',[None,'csrf=secret; Secure; HttpOnly; SameSite=Strict; Path=/',
    '__Host-documind-csrf=secret; HttpOnly; SameSite=Strict; Path=/',
    '__Host-documind-csrf=secret; Secure; HttpOnly; SameSite=Lax; Path=/'])
def test_invalid_secure_cookie_is_permanent_and_redacted(probes,cookie):
    answers,calls,clock=probes;answers.extend([200,200,(200,cookie)]);report={}
    with pytest.raises(deploy.HTTPSProbeError):deploy.https_check(report)
    assert len(calls)==3 and clock[0]==0
    assert report['https_probes'][-1]['cause']=='invalid_csrf_cookie'
    assert 'secret' not in json.dumps(report)


def test_anonymous_document_200_is_a_permanent_security_failure(probes):
    answers,calls,clock=probes;answers.extend([200]*4);report={}
    with pytest.raises(deploy.HTTPSProbeError):deploy.https_check(report)
    assert report['https_probes'][-1]['http_status']==200 and clock[0]==0


@pytest.mark.parametrize('reason,cause,retry',[
    (ssl.SSLCertVerificationError(1,'secret certificate details'),'certificate_verification_failed',False),
    (ssl.SSLError(1,'secret tls details'),'tls_error',False),
    (socket.gaierror(socket.EAI_NONAME,'secret dns details'),'dns_error',False),
    (socket.gaierror(socket.EAI_AGAIN,'secret dns details'),'dns_error',True),
    (ConnectionRefusedError(errno.ECONNREFUSED,'secret endpoint'),'connection_error',True),
    (TimeoutError('secret timeout'),'network_timeout',True),
    ('secret unknown error','network_error',False),
])
def test_network_tls_diagnostics_are_sanitized_and_retry_selective(probes,reason,cause,retry):
    answers,calls,clock=probes;answers.append(deploy.urllib.error.URLError(reason));report={}
    if retry:deploy.https_check(report)
    else:
        with pytest.raises(deploy.HTTPSProbeError) as error:deploy.https_check(report)
        assert 'secret' not in str(error.value)
    event=report['https_probes'][0]
    assert event['cause']==cause and event['retryable']==retry
    assert clock[0]==(2 if retry else 0)
    assert 'secret' not in json.dumps(report)
