import {test} from 'node:test'
import assert from 'node:assert/strict'
import {once} from 'node:events'
import {createSecurityLogger} from './security-audit.mjs'
import {createApp} from './app.mjs'
import {createBffServer} from './http-server.mjs'

const sentinel='SENSITIVE\r\nCOOKIE-PASSWORD-document@example.test'
const service='test-audit-service-credential-not-real-00001'
const config={apiKey:service,upstream:'http://api:8000',allowedHosts:['127.0.0.1'],
  dist:'./nonexistent-audit-test-dist',requireLogin:true,csrfProtection:true,
  gatewayToken:'test-gateway',maxUploadBytes:1024,workerTimeoutMs:1000}

async function serve(t,upstream,sink){
  const server=createBffServer(createApp(config,upstream,{auditSink:sink})).listen(0,'127.0.0.1')
  await once(server,'listening')
  t.after(()=>{server.closeAllConnections();server.close()})
  return `http://127.0.0.1:${server.address().port}`
}

test('security log allowlist rejects control strings, secrets and arbitrary fields',()=>{
  const lines=[]
  const logger=createSecurityLogger(line=>lines.push(JSON.parse(line)))
  assert.ok(logger.emit('access.denied',{password:sentinel,cookie:sentinel,request_id:sentinel,reason_code:sentinel,operation:sentinel,http_status:403}))
  assert.equal(logger.emit(sentinel),false)
  assert.equal(lines.length,1)
  assert.deepEqual(Object.keys(lines[0]).sort(),['timestamp','level','service','event','operation','outcome','http_status'].sort())
  assert.equal(lines[0].operation,'other')
  assert.ok(!JSON.stringify(lines).includes('SENSITIVE'))
})

test('bounded security output drops a flood and contains sink failures',()=>{
  const logger=createSecurityLogger(()=>{throw new Error(sentinel)})
  assert.equal(logger.emit('access.denied'),false)
  assert.equal(logger.stats.failed,1)
  const flood=createSecurityLogger(()=>true)
  // Freeze only this logger's window via synchronous calls; no date/order assertions.
  for(let n=0;n<1000;n++)flood.emit('access.denied')
  assert.ok(flood.stats.dropped>0)
})

test('BFF rejects spoofed request IDs and logs a guard denial without request data',async t=>{
  const lines=[]
  const base=await serve(t,()=>{throw new Error('must not forward')},line=>lines.push(JSON.parse(line)))
  const response=await fetch(base+'/bff/documents?password=SENSITIVE',{headers:{'X-Request-ID':'f'.repeat(32),'cookie':'sentinel-cookie'}})
  assert.equal(response.status,400)
  const id=response.headers.get('x-request-id')
  assert.match(id,/^[0-9a-f]{32}$/)
  assert.notEqual(id,'f'.repeat(32))
  await response.text()
  assert.equal(lines.length,1)
  assert.equal(lines[0].request_id,id)
  assert.equal(lines[0].event,'access.denied')
  assert.ok(!JSON.stringify(lines).includes('SENSITIVE'))
  assert.ok(!JSON.stringify(lines).includes('sentinel-cookie'))
  assert.ok(!JSON.stringify(lines).includes(service))
})

test('one generated correlation ID reaches preflight and upload; API decisions are not duplicated',async t=>{
  const lines=[],calls=[]
  const base=await serve(t,async(url,options)=>{
    calls.push(options.headers['X-Request-ID'])
    if(url.endsWith('/internal/upload-admission'))return new Response(null,{status:204})
    assert.equal(await new Response(options.body).text(),'fictitious content')
    return Response.json({id:'synthetic'},{status:201})
  },line=>lines.push(JSON.parse(line)))
  const secure={'x-forwarded-proto':'https','x-documind-gateway':'test-gateway'}
  const session='A'.repeat(43)
  const initial=await fetch(base+'/bff/auth/csrf',{headers:{...secure,cookie:'__Host-documind='+session}})
  const {csrf_token}=await initial.json()
  const cookie='__Host-documind='+session+'; '+initial.headers.get('set-cookie').split(';')[0]
  const response=await fetch(base+'/bff/documents',{method:'POST',headers:{...secure,cookie,
    'x-csrf-token':csrf_token,'X-Request-ID':'f'.repeat(32),'content-type':'multipart/form-data; boundary=test'},body:'fictitious content'})
  assert.equal(response.status,201)
  assert.deepEqual(calls,[response.headers.get('x-request-id'),response.headers.get('x-request-id')])
  assert.notEqual(calls[0],'f'.repeat(32))
  assert.equal(lines.length,0)
})

test('logger exception does not bypass Host, session or CSRF protection',async t=>{
  const base=await serve(t,()=>{throw new Error('must not forward')},()=>{throw new Error(sentinel)})
  const result=await fetch(base+'/bff/documents')
  assert.equal(result.status,401)
  assert.ok(!(await result.text()).includes('SENSITIVE'))
})

test('invalid upstream session is a local error without leaking the returned value',async t=>{
  const lines=[]
  const base=await serve(t,async()=>Response.json({session_token:sentinel}),line=>lines.push(JSON.parse(line)))
  const secure={'x-forwarded-proto':'https','x-documind-gateway':'test-gateway'}
  const initial=await fetch(base+'/bff/auth/csrf',{headers:secure})
  const {csrf_token}=await initial.json()
  const cookie=initial.headers.get('set-cookie').split(';')[0]
  const response=await fetch(base+'/bff/auth/login',{method:'POST',headers:{...secure,cookie,
    'x-csrf-token':csrf_token,'content-type':'application/json'},body:JSON.stringify({username:'fictitious',password:'SENSITIVE'})})
  assert.equal(response.status,502)
  assert.equal(lines[0].event,'system.worker.failed')
  assert.ok(!JSON.stringify(lines).includes('SENSITIVE'))
  assert.ok(!(await response.text()).includes('SENSITIVE'))
})
