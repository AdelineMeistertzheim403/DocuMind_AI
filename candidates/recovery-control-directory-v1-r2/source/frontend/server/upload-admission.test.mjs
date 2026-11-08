import {test} from 'node:test'
import assert from 'node:assert/strict'
import {once} from 'node:events'
import {createApp} from './app.mjs'
import {createBffServer} from './http-server.mjs'
import {request as httpRequest} from 'node:http'

const token = 'A'.repeat(43)
const config = {
  apiKey: 'test-service-credential-not-real-00001', upstream: 'http://api:8000',
  allowedHosts: ['127.0.0.1'], dist: './nonexistent-test-dist', requireLogin: true,
  csrfProtection: true, gatewayToken: 'test-gateway', maxUploadBytes: 1024,
  workerTimeoutMs: 1000, uploadAuthTimeoutMs: 20, uploadTimeoutMs: 2000,
}

async function setup(t, upstream, overrides={}) {
  const server = createBffServer(createApp({...config,...overrides}, upstream)).listen(0,'127.0.0.1')
  await once(server,'listening')
  t.after(()=>{ server.closeAllConnections(); server.close() })
  const base = `http://127.0.0.1:${server.address().port}`
  const secure = {'x-forwarded-proto':'https','x-documind-gateway':'test-gateway'}
  const response = await fetch(base+'/bff/auth/csrf',{headers:{...secure,cookie:'__Host-documind='+token}})
  const {csrf_token} = await response.json()
  const cookie = '__Host-documind='+token+'; '+response.headers.get('set-cookie').split(';')[0]
  const headers = {...secure,cookie,'x-csrf-token':csrf_token,'content-type':'multipart/form-data; boundary=test'}
  return {base,headers}
}

for (const state of ['invented','expired','revoked','disabled']) {
  test(`upload ${state} session is rejected by preflight before forwarding a body`,async t=>{
    let uploads=0, checks=0
    const {base,headers}=await setup(t,async(url,options)=>{
      if(url.endsWith('/internal/upload-admission')) {
        checks++
        assert.equal(options.method,'GET')
        assert.equal(options.body,undefined)
        assert.equal(options.headers.authorization,'Bearer '+token)
        return Response.json({detail:'Invalid session'},{status:401})
      }
      uploads++
      return Response.json({id:'never'},{status:201})
    })
    const response=await fetch(base+'/bff/documents',{method:'POST',headers,body:'x'.repeat(512)})
    assert.equal(response.status,401)
    assert.equal(checks,1)
    assert.equal(uploads,0)
    assert.match(response.headers.get('set-cookie'),/Max-Age=0/)
  })
}

for(const failure of ['offline','timeout','503','unexpected200']) {
  test(`upload preflight fails closed: ${failure}`,async t=>{
    let uploads=0
    const {base,headers}=await setup(t,async(url,options)=>{
      if(!url.endsWith('/internal/upload-admission')) {uploads++;return Response.json({})}
      if(failure==='offline') throw new Error('private-network-detail')
      if(failure==='timeout') return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}))
      return new Response(null,{status:failure==='503'?503:200})
    })
    const result=await fetch(base+'/bff/documents',{method:'POST',headers,body:'test'})
    assert.equal(result.status,503)
    assert.equal(uploads,0)
    assert.ok(!(await result.text()).includes('private-network-detail'))
  })
}

test('valid upload is transmitted only after preflight; CSRF and route allowlist remain enforced',async t=>{
  const calls=[]
  const {base,headers}=await setup(t,async(url,options)=>{
    calls.push(url)
    if(url.endsWith('/internal/upload-admission')) return new Response(null,{status:204})
    assert.equal(await new Response(options.body).text(),'file-body')
    return Response.json({id:'test'},{status:201})
  })
  assert.equal((await fetch(base+'/bff/documents',{method:'POST',headers:{...headers,'x-csrf-token':'invalid'},body:'ignored'})).status,403)
  assert.equal(calls.length,0)
  assert.equal((await fetch(base+'/bff/documents',{method:'POST',headers,body:'file-body'})).status,201)
  assert.deepEqual(calls,['http://api:8000/api/v1/internal/upload-admission','http://api:8000/api/v1/documents'])
  assert.equal((await fetch(base+'/bff/internal/upload-admission',{headers})).status,404)
})

test('missing/malformed cookie and invalid CSRF never reach preflight',async t=>{
  let calls=0
  const {base,headers}=await setup(t,async()=>{calls++;throw new Error('must not be called')})
  for(const cookie of ['', '__Host-documind=bad']) {
    assert.equal((await fetch(base+'/bff/documents',{method:'POST',headers:{...headers,cookie},body:'body'})).status,401)
  }
  assert.equal(calls,0)
})

test('Expect 100-continue is rejected without requesting a single body byte',async t=>{
  let uploads=0, continues=0
  const {base,headers}=await setup(t,async(url)=>{
    if(url.endsWith('/internal/upload-admission')) return new Response(null,{status:401})
    uploads++;return Response.json({})
  })
  const status=await new Promise((resolve,reject)=>{
    const req=httpRequest(base+'/bff/documents',{method:'POST',headers:{...headers,expect:'100-continue','content-length':'512'}},res=>{
      res.resume();res.on('end',()=>{resolve(res.statusCode);req.destroy()})
    })
    req.on('continue',()=>{continues++;req.end('x'.repeat(512))})
    req.on('error',reject)
    req.setTimeout(1000,()=>{req.destroy();reject(new Error('late authentication'))})
    req.flushHeaders()
  })
  assert.equal(status,401)
  assert.equal(continues,0)
  assert.equal(uploads,0)
})

test('bounded preflight capacity refuses excess without forwarding bodies',async t=>{
  let started
  const checking = new Promise(resolve=>{started=resolve})
  let release
  const gate=new Promise(resolve=>{release=resolve})
  const {base,headers}=await setup(t,async(url)=>{
    assert.ok(url.endsWith('/internal/upload-admission'))
    started();await gate;return new Response(null,{status:401})
  },{uploadMaxPreflights:1,uploadAuthTimeoutMs:1000})
  const pending=fetch(base+'/bff/documents',{method:'POST',headers,body:'first'})
  await checking
  try {assert.equal((await fetch(base+'/bff/documents',{method:'POST',headers,body:'second'})).status,503)}
  finally {release()}
  assert.equal((await pending).status,401)
})

test('slow body returns 408 and releases capacity for the next upload',async t=>{
  const {base,headers}=await setup(t,async(url,options)=>{
    if(url.endsWith('/internal/upload-admission')) return new Response(null,{status:204})
    await Promise.race([
      new Response(options.body).text(),
      new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true})),
    ])
    return Response.json({ok:true},{status:201})
  },{uploadMaxConcurrent:1,uploadIdleTimeoutMs:10})
  const result=await new Promise((resolve,reject)=>{
    const req=httpRequest(base+'/bff/documents',{method:'POST',headers:{...headers,'content-length':'512'}},res=>{
      res.resume();res.on('end',()=>{resolve(res.statusCode);req.destroy()})
    })
    req.on('error',reject)
    req.flushHeaders()
  })
  assert.equal(result,408)
  assert.equal((await fetch(base+'/bff/documents',{method:'POST',headers,body:'next'})).status,201)
})

test('invalid upload timeout and concurrency configurations fail startup',async()=>{
  const {loadConfig}=await import('./config.mjs')
  const env={BFF_SERVICE_KEY:config.apiKey}
  for(const extra of [{UPLOAD_MAX_CONCURRENT:'1.5'}, {UPLOAD_TOTAL_TIMEOUT_SECONDS:'20'},
                      {UPLOAD_READ_TIMEOUT_SECONDS:'2'}, {UPLOAD_MAX_PREFLIGHTS:'0'},
                      {UPLOAD_READ_TIMEOUT_SECONDS:'55',UPLOAD_TOTAL_TIMEOUT_SECONDS:'120'}]) {
    assert.throws(()=>loadConfig({...env,...extra}))
  }
})

test('two active transfers refuse a third and release slots after completion',async t=>{
  let entered=0, ready, release
  const started=new Promise(resolve=>{ready=resolve})
  const gate=new Promise(resolve=>{release=resolve})
  const {base,headers}=await setup(t,async(url,options)=>{
    if(url.endsWith('/internal/upload-admission')) return new Response(null,{status:204})
    await new Response(options.body).text()
    if(++entered===2) ready()
    await gate
    return Response.json({ok:true},{status:201})
  },{uploadMaxConcurrent:2})
  const send=()=>fetch(base+'/bff/documents',{method:'POST',headers,body:'fictitious'})
  const first=send(),second=send()
  await started
  try {assert.equal((await send()).status,503)} finally {release()}
  assert.equal((await first).status,201)
  assert.equal((await second).status,201)
  assert.equal((await send()).status,201)
})

test('disconnect during preflight aborts upstream and recovers admission',async t=>{
  let started, aborted, checks=0
  const checking=new Promise(resolve=>{started=resolve})
  const cancelled=new Promise(resolve=>{aborted=resolve})
  const {base,headers}=await setup(t,async(url,options)=>{
    if(url.endsWith('/internal/upload-admission')) {
      if(++checks>1) return new Response(null,{status:204})
      started()
      return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>{aborted();reject(new Error('disconnected'))},{once:true}))
    }
    await new Response(options.body).text()
    return Response.json({ok:true},{status:201})
  },{uploadMaxPreflights:1,uploadAuthTimeoutMs:1000})
  const req=httpRequest(base+'/bff/documents',{method:'POST',headers:{...headers,'content-length':'512'}})
  req.on('error',()=>{})
  req.flushHeaders()
  await checking
  req.destroy()
  await cancelled
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal((await fetch(base+'/bff/documents',{method:'POST',headers,body:'next'})).status,201)
})

test('disconnect during authorized upload aborts upstream and releases capacity',{timeout:5000},async t=>{
  let started, aborted, released, firstSignal, uploads=0, checks=0
  const receiving=new Promise(resolve=>{started=resolve})
  const cancelled=new Promise(resolve=>{aborted=resolve})
  const closed=new Promise(resolve=>{released=resolve})
  let deadlineTimer
  const deadline=new Promise((_,reject)=>{
    deadlineTimer=setTimeout(()=>reject(new Error('upload disconnect test timed out')),3000)
  })
  t.after(()=>clearTimeout(deadlineTimer))
  const bounded=promise=>Promise.race([promise,deadline])
  const partial='--test\r\nContent-Disposition: form-data; name="file"; filename="test.txt"\r\n\r\npartial'
  const {base,headers}=await setup(t,async(url,options)=>{
    if(url.endsWith('/internal/upload-admission')) {
      checks++
      return new Response(null,{status:204})
    }
    if(++uploads===1) {
      firstSignal=options.signal
      const reader=options.body.getReader()
      reader.closed.then(()=>{},()=>{}).then(()=>{reader.releaseLock();released()})
      const abortEvent=once(options.signal,'abort')
      const chunk=await reader.read()
      started(chunk)
      await abortEvent
      aborted()
      throw new Error('client disconnected')
    }
    assert.equal(await new Response(options.body).text(),'complete upload')
    return Response.json({ok:true},{status:201})
  },{uploadMaxConcurrent:1,uploadAuthTimeoutMs:1000})
  const req=httpRequest(base+'/bff/documents',{method:'POST',headers:{...headers,'content-length':'512'}})
  req.on('error',()=>{})
  t.after(()=>req.destroy())
  req.write(partial)
  const chunk=await bounded(receiving)
  assert.equal(chunk.done,false)
  assert.ok(chunk.value.byteLength>0 && chunk.value.byteLength<512)
  assert.equal(Buffer.from(chunk.value).toString(),partial)
  assert.equal(firstSignal.aborted,false)
  req.destroy()
  await bounded(cancelled)
  assert.equal(firstSignal.aborted,true)
  await bounded(closed)
  const response=await bounded(fetch(base+'/bff/documents',{
    method:'POST',headers,body:'complete upload',signal:AbortSignal.timeout(2000),
  }))
  assert.equal(response.status,201)
  assert.deepEqual(await response.json(),{ok:true})
  assert.equal(checks,2)
  assert.equal(uploads,2)
})
