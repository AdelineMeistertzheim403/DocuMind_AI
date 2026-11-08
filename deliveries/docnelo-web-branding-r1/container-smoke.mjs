// Executed only in the new Web image, --network none, with a loopback mock API.
import http from 'node:http'
import assert from 'node:assert/strict'
import {createApp} from '/app/server/app.mjs'
import {loadConfig} from '/app/server/config.mjs'

let checks=0
const check=(condition,message)=>{assert.ok(condition,message);checks++}
const calls=[]
const upstream=http.createServer((req,res)=>{
  calls.push({method:req.method,path:req.url})
  const path=new URL(req.url,'http://127.0.0.1').pathname
  let value,status=200
  if(path==='/api/v1/health')value={status:'ok',database:'ok'}
  else if(path==='/api/v1/auth/options')value={registration_mode:'disabled',public_capacity_configured:false,public_registration_availability:'closed'}
  else if(path==='/api/v1/auth/login')value={session_token:'A'.repeat(43),expires_in:1800}
  else if(path==='/api/v1/documents')value={items:[],total:0,offset:0,limit:12}
  else{status=404;value={detail:'Unconfigured synthetic route'}}
  req.resume();res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(value))
})
await new Promise(r=>upstream.listen(0,'127.0.0.1',r))
const config=loadConfig({BFF_API_KEY:'s'.repeat(64),BFF_ALLOWED_HOSTS:'documind-r1.test',
  BFF_BACKEND_URL:`http://127.0.0.1:${upstream.address().port}`,BFF_TRUSTED_PROXY_IPS:'127.0.0.1'})
const web=http.createServer(createApp(config))
await new Promise(r=>web.listen(0,'127.0.0.1',r))
const request=(path,{method='GET',headers={},body}={})=>new Promise((resolve,reject)=>{
  const req=http.request({hostname:'127.0.0.1',port:web.address().port,path,method,
    headers:{Host:'documind-r1.test','x-forwarded-proto':'https',...headers}},res=>{
    const parts=[];res.on('data',chunk=>parts.push(chunk));res.on('end',()=>resolve({status:res.statusCode,
      headers:res.headers,body:Buffer.concat(parts).toString()}))
  });req.on('error',reject);req.end(body)
})
try{
  const index=await request('/')
  check(index.status===200,'static index status')
  check(index.body.includes('<title>Docnelo'),'static title')
  const manifest=await request('/manifest.webmanifest')
  check(manifest.status===200&&JSON.parse(manifest.body.replace(/^\uFEFF/, '')).name==='Docnelo','manifest')
  const cssPath=/href="(\/assets\/[^\"]+\.css)"/.exec(index.body)[1]
  const css=await request(cssPath)
  check(css.status===200&&css.body.includes('#126bee'),'compiled brand CSS')
  const logo=await request('/brand/docnelo/docnelo-horizontal-dark-transparent.png')
  check(logo.status===200&&logo.headers['content-type'].includes('image/png'),'logo')
  check((await request('/bff/health')).status===200,'BFF health with loopback API')
  const options=await request('/bff/auth/options')
  check(JSON.parse(options.body).registration_mode==='disabled','registration remains closed in mock')
  check((await request('/bff/documents')).status===401,'anonymous documents denied')
  for(const path of ['/bff/ui-config','/bff/documents/11111111-1111-4111-8111-111111111111/deletion-status',
                    '/bff/documents/11111111-1111-4111-8111-111111111111/download']){
    check((await request(path)).status===404,'new contract must remain absent: '+path)
  }
  const loginBody=JSON.stringify({email:'synthetic@example.test',password:'Synthetic-password-only-123'})
  check((await request('/bff/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:loginBody})).status===403,'CSRF enforcement')
  const protection=await request('/bff/auth/csrf')
  check(protection.status===200,'CSRF endpoint')
  const csrf=JSON.parse(protection.body).csrf_token
  const cookie=protection.headers['set-cookie'][0].split(';')[0]
  check(cookie.startsWith('__Host-documind-csrf='),'CSRF cookie name preserved')
  const login=await request('/bff/auth/login',{method:'POST',headers:{'content-type':'application/json',
    cookie,'x-csrf-token':csrf},body:loginBody})
  check(login.status===200&&JSON.parse(login.body).connected===true,'login through actual BFF')
  const session=login.headers['set-cookie'][0]
  check(session.startsWith('__Host-documind=')&&['HttpOnly','Secure','SameSite=Strict'].every(s=>session.includes(s)), 'session cookie name and flags')
  check((await request('/bff/documents',{headers:{cookie:session.split(';')[0]}})).status===200,'authenticated documents')
  check(calls.some(c=>c.path==='/api/v1/auth/login')&&calls.some(c=>c.path==='/api/v1/documents'),'actual upstream contract used')
  console.log(JSON.stringify({status:'passed',checks,environment:'new image / loopback API / no external network',calls}))
}finally{
  await new Promise(r=>web.close(r));await new Promise(r=>upstream.close(r))
}
