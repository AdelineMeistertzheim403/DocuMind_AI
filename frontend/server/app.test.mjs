import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Readable } from 'node:stream'
import { once } from 'node:events'
import { request as httpRequest } from 'node:http'
import { createApp } from './app.mjs'
import { loadConfig } from './config.mjs'

const key = 'test-server-only-key-00000000000000001'
const id = '11111111-1111-4111-8111-111111111111'
const config = {
  apiKey: key, upstream: 'http://backend:8000', maxUploadBytes: 32, workerTimeoutMs: 1000,
  allowedHosts: ['127.0.0.1', 'localhost'], dist: './nonexistent-test-dist',
}
async function serve(t, upstream, overrides = {}) {
  const server = createApp({ ...config, ...overrides }, upstream).listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => { server.closeAllConnections(); server.close() })
  return `http://127.0.0.1:${server.address().port}`
}

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
  assert.equal((await fetch(network + '/bff/health')).status, 502)
  const redirect = await serve(t, async () => new Response(null, { status: 302, headers: { location: 'https://evil.example' } }))
  assert.equal((await fetch(redirect + '/bff/health')).status, 502)
  const delayed = await serve(t, async (_, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new Error('timeout')), { once: true })), { workerTimeoutMs: 5 })
  assert.equal((await fetch(delayed + '/bff/health')).status, 504)
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
