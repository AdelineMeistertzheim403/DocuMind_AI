import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Readable } from 'node:stream'
import { once } from 'node:events'
import { request as httpRequest } from 'node:http'
import { createApp } from './app.mjs'
import { loadConfig } from './config.mjs'
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { fileURLToPath } from 'node:url'

const key = 'test-server-only-key-00000000000000001'
const id = '11111111-1111-4111-8111-111111111111'

test('production Docker healthcheck sends the exact allowed Host and preserves security', async t => {
  const domain = 'documind.adelinemeistertzheim.fr'
  const env = { BFF_SERVICE_KEY: key, BFF_BACKEND_URL: 'http://api:8000', BFF_HOST: '0.0.0.0',
    BFF_PORT: '3000', BFF_ALLOWED_HOSTS: domain, BFF_TRUSTED_PROXY_IPS: '192.0.2.10' }
  const production = loadConfig(env)
  let host, healthy = true, upstreamCalls = 0
  const app = createApp(production, async (url, options) => {
    upstreamCalls++
    assert.equal(url, 'http://api:8000/api/v1/health')
    assert.equal(options.headers['X-API-Key'], key)
    assert.equal(options.headers.authorization, undefined)
    return Response.json({ private: 'never exposed' }, { status: healthy ? 200 : 503 })
  })
  const server = createServer((req, res) => { host = req.headers.host; app(req, res) }).listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => { server.closeAllConnections(); server.close() })
  const port = server.address().port
  const probe = async overrides => {
    const child = spawn(process.execPath, ['server/healthcheck.mjs'], {
      cwd: fileURLToPath(new URL('../', import.meta.url)),
      env: { ...process.env, ...env, BFF_PORT: String(port), ...overrides }, stdio: 'ignore',
    })
    const [code] = await once(child, 'exit')
    return code
  }
  assert.equal(await probe(), 0)
  assert.equal(host, domain)
  const raw = (path, headers = {}, method = 'GET') => new Promise((resolve, reject) => {
    const req = httpRequest({ hostname: '127.0.0.1', port, path, method, headers: { Host: domain, ...headers } }, res => {
      let body = ''; res.on('data', chunk => { body += chunk }); res.on('end', () => resolve({ status: res.statusCode, body, headers: res.headers }))
    })
    req.on('error', reject); req.end()
  })
  const result = await raw('/bff/health')
  assert.equal(result.status, 200)
  assert.deepEqual(JSON.parse(result.body), { status: 'ok' })
  assert.equal(result.headers['cache-control'], 'no-store')
  assert.equal(result.headers['set-cookie'], undefined)
  assert.equal((await raw('/bff/health', { Host: '127.0.0.1' })).status, 403)
  assert.equal((await raw('/bff/health', { Host: 'evil.test', 'x-forwarded-host': domain })).status, 403)
  assert.equal((await raw('/bff/health', { origin: 'https://evil.test' })).status, 403)
  assert.equal((await raw('/bff/health?url=http://evil.test')).status, 400)
  assert.equal((await raw('/bff/health', {}, 'POST')).status, 404)
  assert.equal((await raw('/bff/documents')).status, 401)
  assert.equal((await raw('/bff/ai/settings', { 'x-forwarded-proto': 'https' })).status, 403)
  assert.equal(await probe({ BFF_ALLOWED_HOSTS: 'evil.test' }), 1)
  assert.equal(upstreamCalls, 2)
  healthy = false
  assert.equal(await probe(), 1)
})

test('health explicitly reports unavailable when the API cannot be reached', async t => {
  const base = await serve(t, async () => { throw new Error('offline') })
  assert.equal((await fetch(base + '/bff/health')).status, 503)
})
const config = {
  apiKey: key, upstream: 'http://backend:8000', maxUploadBytes: 32, workerTimeoutMs: 1000,
  allowedHosts: ['127.0.0.1', 'localhost'], dist: './nonexistent-test-dist',
}

test('public registration endpoints require HTTPS and CSRF but no existing session',async t=>{
  const calls=[]
  const base=await serve(t,async(url,options)=>{
    calls.push({url,options})
    if(url.endsWith('/auth/registration-challenge'))return Response.json({challenge:'fictitious'})
    await new Response(options.body).text()
    return Response.json({verified:true})
  },{requireLogin:true,csrfProtection:true,gatewayToken:'gateway'})
  const headers={'x-forwarded-proto':'https','x-documind-gateway':'gateway'}
  assert.equal((await fetch(base+'/bff/auth/registration-challenge')).status,403)
  assert.equal((await fetch(base+'/bff/auth/registration-challenge',{headers})).status,200)
  for(const path of ['/bff/auth/verify-email','/bff/auth/resend-verification']){
    assert.equal((await fetch(base+path,{method:'POST',headers:{...headers,'content-type':'application/json'},body:'{}'})).status,403)
    const csrf=await fetch(base+'/bff/auth/csrf',{headers})
    const {csrf_token}=await csrf.json()
    const cookie=csrf.headers.get('set-cookie').split(';')[0]
    const response=await fetch(base+path,{method:'POST',headers:{...headers,cookie,'x-csrf-token':csrf_token,'content-type':'application/json'},body:'{}'})
    assert.equal(response.status,200)
  }
  assert.equal(calls.length,3)
  assert.ok(calls.every(call=>call.options.headers['X-API-Key']===key&&call.options.headers['x-documind-secure']==='1'))
  assert.equal((await fetch(base+'/bff/account',{headers})).status,401)
})
async function serve(t, upstream, overrides = {}) {
  const server = createApp({ ...config, ...overrides }, upstream).listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => { server.closeAllConnections(); server.close() })
  return `http://127.0.0.1:${server.address().port}`
}

test('disabled AI refusal is sanitized while key deletion and local routes keep HTTPS and CSRF', async t => {
  const calls = []
  const base = await serve(t, async (url, options) => {
    calls.push({url, options})
    if (options.method === 'POST') return Response.json({detail:{code:'disabled',message:`private ${key}`}},{status:403})
    return Response.json({key_connected:false})
  }, {requireLogin:true,csrfProtection:true,gatewayToken:'fictitious-gateway'})
  const secure = {'x-forwarded-proto':'https','x-documind-gateway':'fictitious-gateway'}
  const session = 'A'.repeat(43), cookie = '__Host-documind=' + session
  const protection = await fetch(base + '/bff/auth/csrf',{headers:{...secure,cookie}})
  const {csrf_token} = await protection.json()
  const headers = {...secure,cookie:cookie+'; '+protection.headers.get('set-cookie').split(';')[0],
    'x-csrf-token':csrf_token,'content-type':'application/json'}
  for (const path of ['/ai/key','/ai/key/validate',`/documents/${id}/summarize`]) {
    const response = await fetch(base+'/bff'+path,{method:'POST',headers,body:'{}'})
    assert.equal(response.status,403)
    const data = await response.json()
    assert.equal(data.code,'disabled')
    assert.match(data.detail,/disponibles ultérieurement/)
    assert.ok(!JSON.stringify(data).includes(key))
    assert.equal(calls.at(-1).options.headers.authorization,'Bearer '+session)
  }
  assert.equal((await fetch(base+'/bff/ai/key',{method:'DELETE',headers})).status,200)
  assert.equal((await fetch(base+'/bff/documents',{headers})).status,200)
  const count = calls.length
  assert.equal((await fetch(base+'/bff/ai/key',{method:'DELETE',headers:{...headers,'x-csrf-token':'wrong'}})).status,403)
  assert.equal(calls.length,count)
})

test('clé ajoutée côté serveur seulement et pagination transmise', async t => {
  let forwarded
  const base = await serve(t, async (url, options) => {
    forwarded = { url, options }
    return Response.json({ items: [], total: 0, offset: 12, limit: 12 })
  })
  const result = await fetch(`${base}/bff/documents?offset=12&limit=12`, { headers: { 'X-API-Key': 'untrusted-client-key' } })
  assert.equal(result.status, 200)
  assert.equal(forwarded.url, 'http://backend:8000/api/v1/documents?offset=12&limit=12')
  assert.equal(forwarded.options.headers['X-API-Key'], key)
  assert.equal(forwarded.options.redirect, 'manual')
  assert.equal(result.headers.get('cache-control'), 'no-store')
  assert.ok(!(await result.text()).includes(key))
})

test('download routes require the personal session and stream only validated upstream metadata', async t => {
  const calls = []
  const base = await serve(t, async (url, options) => {
    calls.push({url, options})
    return new Response(Readable.toWeb(Readable.from(['original bytes'])), {
      headers: {
        'content-length': '14',
        'content-type': 'text/plain; charset=utf-8',
        'content-disposition': `attachment; filename="document-${id}.txt"; filename*=UTF-8''rapport%20final.txt`,
      },
    })
  }, {requireLogin:true, gatewayToken:'gateway'})
  const path = `/bff/documents/${id}/download`
  assert.equal((await fetch(base + path)).status, 401)
  const response = await fetch(base + path, {headers:{
    'x-forwarded-proto':'https', 'x-documind-gateway':'gateway', cookie:'__Host-documind='+'A'.repeat(43),
  }})
  assert.equal(response.status, 200)
  assert.equal(await response.text(), 'original bytes')
  assert.equal(response.headers.get('content-disposition'), `attachment; filename="document-${id}.txt"; filename*=UTF-8''rapport%20final.txt`)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].options.headers.authorization, 'Bearer ' + 'A'.repeat(43))
  assert.equal(calls[0].options.headers.accept, 'application/octet-stream')
})

test('expired download session is rejected and cleared by the BFF', async t => {
  const base = await serve(t, async () => Response.json({detail:'expired'}, {status:401}),
    {requireLogin:true, gatewayToken:'gateway'})
  const response = await fetch(base + `/bff/documents/${id}/download`, {headers:{
    'x-forwarded-proto':'https', 'x-documind-gateway':'gateway', cookie:'__Host-documind='+'A'.repeat(43),
  }})
  assert.equal(response.status, 401)
  assert.match(response.headers.get('set-cookie'), /__Host-documind=;/)
})

test('download BFF refuses an oversized or malformed upstream response', async t => {
  const base = await serve(t, async () => new Response('unsafe', {headers:{
    'content-length':'33', 'content-type':'text/plain',
    'content-disposition':'attachment; filename="unsafe.txt"',
  }}), {requireLogin:true, gatewayToken:'gateway'})
  const response = await fetch(base + `/bff/documents/${id}/download`, {headers:{
    'x-forwarded-proto':'https', 'x-documind-gateway':'gateway', cookie:'__Host-documind='+'A'.repeat(43),
  }})
  assert.equal(response.status, 502)
  assert.match((await response.json()).detail, /récupéré en sécurité/)
})
test('configuration publique limitée à la taille autorisée', async t => {
  const base = await serve(t, () => assert.fail('No upstream call expected'))
  const result = await fetch(`${base}/bff/config`)
  assert.deepEqual(await result.json(), { max_upload_bytes: 32 })
})
test('refuse proxy arbitraire, méthodes, chemins et paramètres inconnus', async t => {
  let calls = 0
  const base = await serve(t, () => { calls++; return Response.json({}) })
  for (const path of ['/bff/proxy?url=http://evil', '/bff/documents/not-a-uuid', '/bff/documents?url=http://evil', '/bff/documents?limit=1000', '/bff/documents?offset=-1', '/bff/documents?limit=1&limit=2', `/bff/documents/${id}/analysis?x=1`]) {
    assert.ok([400, 404].includes((await fetch(base + path)).status))
  }
  assert.equal((await fetch(`${base}/bff/documents/${id}`, { method: 'PUT' })).status, 404)
  assert.equal(calls, 0)
})
test('refuse les origines étrangères et le DNS rebinding', async t => {
  const base = await serve(t, () => assert.fail('No upstream call expected'))
  assert.equal((await fetch(`${base}/bff/documents`, { headers: { origin: 'https://evil.example' } })).status, 403)
  const rebindingStatus = await new Promise((resolve, reject) => {
    const request = httpRequest(`${base}/bff/documents`, { headers: { Host: 'evil.example' } }, response => { response.resume(); resolve(response.statusCode) })
    request.on('error', reject); request.end()
  })
  assert.equal(rebindingStatus, 403)
  assert.equal((await fetch(`${base}/bff/documents`, { headers: { 'sec-fetch-site': 'cross-site' } })).status, 403)
})
test('transmet le multipart et le corps JSON aux seules routes autorisées', async t => {
  const calls = []
  const base = await serve(t, async (url, options) => {
    const text = await new Response(options.body).text()
    calls.push({ url, text, contentType: options.headers['content-type'] })
    return Response.json({ id }, { status: 201 })
  }, { maxUploadBytes: 1024 })
  const form = new FormData(); form.append('file', new Blob(['Texte de test']), 'test.txt')
  assert.equal((await fetch(`${base}/bff/documents`, { method: 'POST', body: form })).status, 201)
  assert.match(calls[0].text, /Texte de test/)
  assert.match(calls[0].contentType, /^multipart\/form-data; boundary=/)
  assert.equal((await fetch(`${base}/bff/documents/${id}/analyze`, { method: 'POST', body: '{}', headers: { 'content-type': 'application/json' } })).status, 201)
  assert.equal(calls[1].text, '{}')
})
test('gère DELETE 204 sans corps', async t => {
  const base = await serve(t, async () => new Response(null, { status: 204 }))
  const result = await fetch(`${base}/bff/documents/${id}`, { method: 'DELETE' })
  assert.equal(result.status, 204)
  assert.equal(await result.text(), '')
})
for (const status of [401, 404, 413, 415, 422, 503]) {
  test(`erreur ${status} contrôlée sans fuite de clé ou de détail interne`, async t => {
    const base = await serve(t, async () => Response.json({ detail: `private traceback ${key}` }, { status }))
    const response = await fetch(`${base}/bff/documents`)
    assert.equal(response.status, status)
    const text = await response.text()
    assert.ok(!text.includes(key) && !text.includes('traceback'))
  })
}
test('erreur réseau, redirection et délai contrôlés', async t => {
  const network = await serve(t, async () => { throw new Error('private url') })
  assert.equal((await fetch(network + '/bff/documents')).status, 502)
  const redirect = await serve(t, async () => new Response(null, { status: 302, headers: { location: 'https://evil.example' } }))
  assert.equal((await fetch(redirect + '/bff/documents')).status, 502)
  const delayed = await serve(t, async (_, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('timeout')), { once: true })), { workerTimeoutMs: 5 })
  assert.equal((await fetch(delayed + '/bff/documents')).status, 504)
})
test('rejette les corps trop grands, y compris en flux sans Content-Length', async t => {
  const base = await serve(t, async (_, options) => {
    await new Response(options.body).text()
    return Response.json({})
  })
  const options = { method: 'POST', headers: { 'content-type': 'multipart/form-data; boundary=test' } }
  assert.equal((await fetch(`${base}/bff/documents`, { ...options, body: 'a'.repeat(70000) })).status, 413)
  const response = await fetch(`${base}/bff/documents`, { ...options, body: Readable.toWeb(Readable.from(['a'.repeat(35000), 'b'.repeat(35000)])), duplex: 'half' })
  assert.equal(response.status, 413)
})
test('configuration serveur validée sans clé publique VITE', () => {
  const loaded = loadConfig({ API_KEYS: JSON.stringify({ [key]: id }), API_PORT: '8001' })
  assert.equal(loaded.apiKey, key)
  assert.equal(loaded.upstream, 'http://127.0.0.1:8001')
  assert.throws(() => loadConfig({ API_KEYS: '{}' }))
  assert.throws(() => loadConfig({ API_KEYS: JSON.stringify({ [key]: id, ['b'.repeat(32)]: id }) }))
  assert.throws(() => loadConfig({ BFF_API_KEY: key, BFF_BACKEND_URL: 'file:///tmp/secrets' }))
})

test('refuse les clés personnelles sur HTTP et les faux en-têtes HTTPS', async t => {
  let calls=0
  const base=await serve(t,async()=>{calls++;return Response.json({})})
  for(const headers of [{}, {'x-forwarded-proto':'https','x-documind-gateway':'forged'}]) {
    const response=await fetch(base+'/bff/ai/key',{method:'POST',headers:{...headers,'content-type':'application/json'},body:JSON.stringify({api_key:'test-personal-key'})})
    assert.equal(response.status,403)
  }
  assert.equal(calls,0)
})
test('session opaque en cookie sécurisé, jamais dans la réponse navigateur', async t => {
  const token='a'.repeat(43), gateway='gateway-test-token-not-real-secret'
  const calls=[]
  const base=await serve(t,async(url,options)=>{
    calls.push({url,options})
    if(url.endsWith('/auth/login')) return Response.json({session_token:token,expires_in:1800})
    return Response.json({username:'alice',key_connected:true})
  },{gatewayToken:gateway})
  const headers={'x-forwarded-proto':'https','x-documind-gateway':gateway,'content-type':'application/json'}
  const login=await fetch(base+'/bff/auth/login',{method:'POST',headers,body:JSON.stringify({username:'alice',password:'test-password-not-secret'})})
  assert.deepEqual(await login.json(),{connected:true})
  const cookie=login.headers.get('set-cookie')
  for(const attribute of ['HttpOnly','Secure','SameSite=Strict','Path=/'])assert.ok(cookie.includes(attribute))
  await fetch(base+'/bff/ai/settings',{headers:{...headers,cookie:`__Host-documind=${token}`}})
  assert.equal(calls[1].options.headers.authorization,`Bearer ${token}`)
  assert.equal(calls[1].options.headers['x-documind-secure'],'1')
})
test('traitements IA protégés et erreurs budgétaires contrôlées', async t=>{
  const gateway='gateway-test-token-not-real-secret'
  const base=await serve(t,async()=>Response.json({detail:{code:'budget_exhausted',message:`private ${key}`}},{status:402}),{gatewayToken:gateway})
  const path=base+`/bff/documents/${id}/summarize`
  assert.equal((await fetch(path,{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).status,403)
  const response=await fetch(path,{method:'POST',headers:{'content-type':'application/json','x-forwarded-proto':'https','x-documind-gateway':gateway,cookie:'__Host-documind='+'a'.repeat(43)},body:'{}'})
  assert.equal(response.status,402)
  const data=await response.json()
  assert.equal(data.code,'budget_exhausted')
  assert.ok(!JSON.stringify(data).includes(key))
})

test('routes Sprint 4 bornées : session HTTPS pour indexation, recherche et synthèse',async t=>{
  const calls=[],gateway='test-sprint4-private-gateway'
  const base=await serve(t,async(url,options)=>{calls.push({url,options});return Response.json({ok:true})},{gatewayToken:gateway})
  for(const path of [`/documents/${id}/index`,'/search/semantic','/search/ask',`/comparisons/${id}/summarize`,`/documents/${id}/summary-jobs`,`/summary-jobs/${id}/resume`,`/summary-jobs/${id}/cancel`]) {
    const opts={method:'POST',headers:{'content-type':'application/json'},body:'{}'}
    assert.equal((await fetch(base+'/bff'+path,opts)).status,403)
    assert.equal((await fetch(base+'/bff'+path,{...opts,headers:{...opts.headers,'x-forwarded-proto':'https','x-documind-gateway':gateway,cookie:'__Host-documind='+'a'.repeat(43)}})).status,200)
    assert.equal(calls.at(-1).options.headers.authorization,'Bearer '+'a'.repeat(43))
  }
  assert.equal((await fetch(base+'/bff/documents/compare',{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).status,200)
  assert.equal((await fetch(base+`/bff/comparisons/${id}`)).status,200)
  assert.equal((await fetch(base+`/bff/comparisons/${id}/arbitrary`)).status,404)
})


test('SaaS refuses document access without a personal session',async t=>{
  const base=await serve(t,()=>assert.fail('No fallback to shared owner'),{requireLogin:true,gatewayToken:'gateway'})
  assert.equal((await fetch(base+'/bff/documents')).status,401)
  assert.equal((await fetch(base+'/bff/documents',{headers:{'x-forwarded-proto':'https','x-documind-gateway':'gateway'}})).status,401)
})

test('signed CSRF is mandatory and bound to the authenticated session',async t=>{
  let calls=0
  const base=await serve(t,async()=>{calls++;return Response.json({ok:true})},{requireLogin:true,csrfProtection:true,gatewayToken:'gateway'})
  const secure={'x-forwarded-proto':'https','x-documind-gateway':'gateway'}
  const session='A'.repeat(43),cookie='__Host-documind='+session
  const protect=await fetch(base+'/bff/auth/csrf',{headers:{...secure,cookie}})
  const {csrf_token}=await protect.json()
  const csrfCookie=protect.headers.get('set-cookie').split(';')[0]
  const send=(headers)=>fetch(base+'/bff/account/password',{method:'POST',headers:{...secure,'content-type':'application/json',cookie:cookie+'; '+csrfCookie,...headers},body:'{}'})
  assert.equal((await send({})).status,403)
  assert.equal((await send({'x-csrf-token':'wrong'})).status,403)
  assert.equal((await send({'x-csrf-token':csrf_token,cookie:'__Host-documind='+'B'.repeat(43)+'; '+csrfCookie})).status,403)
  assert.equal(calls,0)
  assert.equal((await send({'x-csrf-token':csrf_token})).status,200)
  assert.equal(calls,1)
  assert.ok(!csrf_token.includes(key) && !csrf_token.includes(session))
})

test('Traefik: exact TCP peer is trusted, forwarded headers alone are refused',async t=>{
  const upstream=[]
  const base=await serve(t,async(url,options)=>{upstream.push(options);return Response.json({ok:true})},
    {trustedProxyIPs:['127.0.0.1'],requireLogin:true})
  const headers={'x-forwarded-proto':'https','x-forwarded-for':'203.0.113.10',cookie:'__Host-documind='+'A'.repeat(43)}
  assert.equal((await fetch(base+'/bff/ai/settings',{headers})).status,200)
  assert.equal(upstream[0].headers['x-documind-secure'],'1')
  assert.equal(upstream[0].headers['x-documind-client-ip'],'203.0.113.10')
  const refused=await serve(t,()=>assert.fail('Untrusted peer'),{trustedProxyIPs:['127.0.0.2'],requireLogin:true})
  assert.equal((await fetch(refused+'/bff/ai/settings',{headers})).status,403)
  assert.equal((await fetch(base+'/bff/ai/settings',{headers:{...headers,'x-forwarded-proto':'http'}})).status,403)
})

test('Traefik: secure cookies and CSRF remain enforced behind TLS termination',async t=>{
  const base=await serve(t,async()=>Response.json({session_token:'B'.repeat(43),expires_in:1800}),
    {trustedProxyIPs:['127.0.0.1'],csrfProtection:true,requireLogin:true})
  const headers={'x-forwarded-proto':'https','content-type':'application/json'}
  const url=base+'/bff/auth/login'
  assert.equal((await fetch(url,{method:'POST',headers,body:'{}'})).status,403)
  const protection=await fetch(base+'/bff/auth/csrf',{headers})
  const {csrf_token}=await protection.json()
  const cookie=protection.headers.get('set-cookie').split(';')[0]
  const response=await fetch(url,{method:'POST',headers:{...headers,cookie,'x-csrf-token':csrf_token},body:'{}'})
  assert.equal(response.status,200)
  assert.deepEqual(await response.json(),{connected:true})
  for(const flag of ['HttpOnly','Secure','SameSite=Strict'])assert.ok(response.headers.get('set-cookie').includes(flag))
  assert.throws(()=>loadConfig({BFF_API_KEY:key,BFF_TRUSTED_PROXY_IPS:'0.0.0.0/0'}))
})
