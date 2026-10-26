// A real desktop/mobile Chromium signup. No fixture accounts, API mocks or SMTP shortcuts.
import {chromium,devices} from '../../frontend/node_modules/@playwright/test/index.mjs'
import assert from 'node:assert/strict'
import {once} from 'node:events'
import {createInterface} from 'node:readline'

const messages=createInterface({input:process.stdin})
const [line]=await once(messages,'line')
const config=JSON.parse(line)
const args=[`--ignore-certificate-errors-spki-list=${config.spki}`]
if(new URL(config.origin).hostname==='documind.test')args.push('--host-resolver-rules=MAP documind.test 127.0.0.1')
const email=config.email||'browser@example.test'
const browser=await chromium.launch({headless:true,args})
try{
  const context=await browser.newContext(config.mobile?{...devices['iPhone 13']}: {})
  await context.route('**/*',route=>new URL(route.request().url()).origin===config.origin?route.continue():route.abort())
  const page=await context.newPage()
  await page.goto(config.origin+'/register')
  const checkbox=page.getByRole('checkbox')
  await checkbox.waitFor();assert.equal(await checkbox.isChecked(),false)
  await page.getByLabel('Email',{exact:true}).fill(email)
  await page.getByLabel('Mot de passe',{exact:true}).fill(config.password)
  await checkbox.check()
  await page.getByRole('button',{name:'Inscription',exact:true}).click()
  await page.getByText('Demande reçue.',{exact:false}).waitFor({timeout:25000})
  console.log('registered')
  const [response]=await once(messages,'line')
  const {token}=JSON.parse(response)
  await page.goto(config.origin+'/verify-email#token='+token)
  await page.getByLabel('Mot de passe',{exact:true}).fill(config.password)
  await page.getByRole('button',{name:'Vérifier mon adresse e-mail',exact:true}).click()
  await page.getByText('Adresse vérifiée.',{exact:false}).waitFor()
  assert.equal(new URL(page.url()).hash,'')
  await page.goto(config.origin+'/login')
  await page.getByLabel('Email ou identifiant historique').fill(email)
  await page.getByLabel('Mot de passe',{exact:true}).fill(config.password)
  await page.getByRole('button',{name:'Connexion',exact:true}).click()
  await page.getByRole('heading',{name:'Tableau de bord'}).waitFor()
  // Same browser session, full HTTPS BFF -> API upload admission and local analysis.
  const result=await page.evaluate(async()=>{
    async function csrf(){return (await(await fetch('/bff/auth/csrf')).json()).csrf_token}
    const body=new FormData();body.append('file',new File(['Fictitious beta document. Only local text analysis.'],'fictitious.txt',{type:'text/plain'}))
    const uploaded=await fetch('/bff/documents',{method:'POST',headers:{'X-CSRF-Token':await csrf()},body})
    const document=await uploaded.json()
    const analysis=await fetch(`/bff/documents/${document.id}/analyze`,{method:'POST',headers:{'X-CSRF-Token':await csrf(),'Content-Type':'application/json'},body:'{}'})
    const ai=await fetch('/bff/ai/key',{method:'POST',headers:{'X-CSRF-Token':await csrf(),'Content-Type':'application/json'},body:JSON.stringify({api_key:'sk-fictitious-never-sent-to-provider'})})
    return {upload:uploaded.status,analysis:analysis.status,ai:ai.status}
  })
  assert.deepEqual(result,{upload:201,analysis:201,ai:403})
  const cookies=await context.cookies()
  const session=cookies.find(value=>value.name==='__Host-documind')
  assert.ok(session?.secure&&session.httpOnly&&session.sameSite==='Strict')
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0)
  console.log('completed')
}finally{await browser.close();messages.close()}
