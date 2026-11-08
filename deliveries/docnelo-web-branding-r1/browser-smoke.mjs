// Local compiled CSS/JS only. All network requests are fulfilled or rejected here.
import {chromium} from './source/frontend/node_modules/@playwright/test/index.mjs'
import {readFile, writeFile, mkdir} from 'node:fs/promises'
import {resolve, extname, sep} from 'node:path'
import assert from 'node:assert/strict'

const root = resolve(import.meta.dirname)
const baseline = process.env.R1_BASELINE === '1'
const dist = resolve(root, baseline ? 'baseline-dist' : 'source/frontend/dist')
const evidence = resolve(root, baseline ? 'baseline-browser-evidence' : 'browser-evidence')
await mkdir(evidence, {recursive:true})
const browser = await chromium.launch({headless:true, executablePath:process.env.R1_CHROMIUM})
const origin = 'https://documind-r1.test'
const documentId = '11111111-1111-4111-8111-111111111111'
const document = {id:documentId, filename:'Synthetic-R1.txt', media_type:'text/plain',size_bytes:24,
  sha256:'a'.repeat(64),created_at:'2026-10-19T08:00:00Z',
  pages:[{id:'page-1',page_number:1,text:'Synthetic document for local branding verification.'}]}
const options = {registration_mode:'disabled',public_capacity_configured:false,
  public_registration_availability:'closed',terms_version:'historical-test-v1',
  terms_url:'https://legal.example.test/historical-test-v1',
  privacy_url:'https://legal.example.test/privacy',legal_notice_url:'https://legal.example.test/notice',
  operator_name:'Synthetic operator',contact_email:'contact@example.test'}
const results=[]
const requests=[]
const unexpected=[]
try {
  for (const [format, viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
    const context=await browser.newContext({viewport})
    let logged=false
    const errors=[]
    await context.route('**/*',async route=>{
      const request=route.request(), url=new URL(request.url()), path=url.pathname
      requests.push({format,method:request.method(),path})
      if(url.origin!==origin){unexpected.push(url.origin+path);return route.abort()}
      if(path.startsWith('/bff/')){
        let value,status=200
        if(path==='/bff/auth/options')value=options
        else if(path==='/bff/auth/csrf')value={csrf_token:'synthetic-token'}
        else if(path==='/bff/auth/login' && request.method()==='POST'){logged=true;value={connected:true}}
        else if(path==='/bff/account'){
          status=logged?200:401
          value=logged?{id:'synthetic-user',email:'test@example.test',username:'synthetic',owner_id:'synthetic-owner',workspace:'Espace personnel'}:{detail:'Session requise'}
        }
        else if(path==='/bff/account/sessions')value={items:[]}
        else if(path==='/bff/health')value={status:'ok',database:'ok'}
        else if(path==='/bff/config')value={max_upload_bytes:10485760}
        else if(path==='/bff/documents')value={items:[document],total:1,offset:0,limit:12}
        else if(path===`/bff/documents/${documentId}`)value=document
        else if(path===`/bff/documents/${documentId}/analysis`){status=404;value={detail:'No synthetic analysis'}}
        else if(path===`/bff/documents/${documentId}/summary-plan`)value={direct:true,parts:1,steps:1,levels:1,
          root:'map-0',summary_chars:100,pages_total:1,empty_pages:[],maximum_usd:0,input_limit:16000,overlap_chars:200}
        else if(path==='/bff/ai/status')value={mode:'USER_BYOK',enabled:false,available:false,reason:'disabled',
          provider:'openai',model:'disabled',budget_usd:0,spent_usd:0,reserved_usd:0,remaining_usd:0,
          summary_quota:0,question_quota:0,summaries_used:0,questions_used:0,requests:0,provider_calls:0,
          input_tokens:0,output_tokens:0,reasoning_tokens:0,pending_requests:0,pricing_verified_on:''}
        else if(path==='/bff/ai/settings')value={username:'synthetic',owner_id:'synthetic-owner',mode:'USER_BYOK',
          limit_usd:0,key_connected:false,key_validated:false,expires_at:2000000000}
        else if(path==='/bff/ai/consumption')value={mode:'USER_BYOK',limit_usd:0,spent_usd:0,reserved_usd:0,
          remaining_usd:0,input_tokens:0,output_tokens:0,reasoning_tokens:0,provider_calls:0}
        else if(path==='/bff/ai/usage')value={items:[],total:0,offset:0,limit:20}
        else if(path===`/bff/documents/${documentId}/summaries`||path===`/bff/documents/${documentId}/ai-history`)value={items:[],total:0,offset:0,limit:10}
        else {unexpected.push(path);status=404;value={detail:'Unexpected mock request'}}
        return route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)})
      }
      let file=resolve(dist,'.'+decodeURIComponent(path))
      if(file!==dist && !file.startsWith(dist+sep)){return route.abort()}
      if(!extname(path))file=resolve(dist,'index.html')
      try{
        const body=await readFile(file)
        const contentType={'.html':'text/html','.js':'application/javascript','.css':'text/css',
          '.png':'image/png','.ico':'image/x-icon','.svg':'image/svg+xml','.webmanifest':'application/manifest+json'}[extname(file)]||'application/octet-stream'
        return route.fulfill({status:200,contentType,body})
      }catch{unexpected.push(path);return route.fulfill({status:404,body:'missing asset'})}
    })
    const page=await context.newPage()
    page.on('pageerror',error=>errors.push(String(error)))
    await page.goto(origin+'/login')
    await page.getByRole('heading',{name:'Connexion',exact:true}).waitFor()
    if (!baseline) await page.locator('.brand-logo').evaluate(img=>img.decode())
    assert.equal(await page.title(),baseline ? 'DocuMind AI — Votre espace documentaire' : 'Docnelo — Votre espace documentaire')
    const css=await page.evaluate(()=>({blue:getComputedStyle(document.documentElement).getPropertyValue('--docnelo-blue').trim(),
      mint:getComputedStyle(document.documentElement).getPropertyValue('--docnelo-mint').trim(),
      logoWidth:document.querySelector('.brand-logo')?.getBoundingClientRect().width || 0,
      primary:getComputedStyle(document.querySelector('.button.primary')).backgroundColor,
      overflow:document.documentElement.scrollWidth>innerWidth}))
    if (!baseline) {
      assert.equal(css.blue.toLowerCase(),'#126bee');assert.equal(css.mint.toLowerCase(),'#3ad8b4');assert.equal(css.logoWidth,160)
      assert.match(css.primary,/18, 107, 238/);assert.equal(css.overflow,false)
      assert.ok(await page.getByText('Public Beta',{exact:true}).isVisible())
    }
    await page.screenshot({path:resolve(evidence,format+'-login.png'),fullPage:true})
    results.push({format,path:'/login',passed:true,computedCss:css})
    await page.goto(origin+'/register')
    await page.getByText('Les nouvelles inscriptions sont fermées. Les comptes existants restent accessibles.').waitFor()
    assert.equal(await page.getByRole('button',{name:'Inscription',exact:true}).isDisabled(),true)
    results.push({format,path:'/register',passed:true,registration:'disabled in synthetic options'})
    await page.goto(origin+'/login')
    await page.getByLabel('Email ou identifiant historique').fill('synthetic@example.test')
    await page.getByLabel('Mot de passe',{exact:true}).fill('Synthetic-password-only-123')
    await page.getByRole('button',{name:'Connexion',exact:true}).click()
    await page.getByRole('heading',{name:'Tableau de bord',exact:true}).waitFor()
    if(format==='mobile'){
      await page.getByRole('button',{name:'Ouvrir le menu'}).click()
      await page.getByRole('dialog',{name:'Navigation principale'}).waitFor()
      await page.locator('.nav-list').getByRole('link',{name:'Documents',exact:true}).click()
      await page.getByRole('heading',{name:'Documents',exact:true}).waitFor()
    }
    const screens=[['/','Tableau de bord'],['/documents','Documents'],[`/documents/${documentId}`,'Synthetic-R1.txt'],
      ['/settings/ai','Paramètres IA'],['/settings/profile','Profil'],['/settings/security','Sécurité'],
      ['/settings/privacy','Confidentialité'],['/legal',baseline ? 'Informations sur la bêta DocuMind AI' : 'Informations sur la bêta Docnelo']]
    for(const [path,title] of screens){
      await page.goto(origin+path)
      await page.getByRole('heading',{name:title,exact:true}).waitFor()
      const layout=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
        outside:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1 && r.width>0}).slice(0,14).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right}))}))
      if(layout.scrollWidth>layout.width)console.log(JSON.stringify({format,path,layout}))
      if (!baseline) assert.equal(layout.scrollWidth>layout.width,false,format+path+' overflows')
      if(path==='/legal')assert.equal(await page.getByRole('link',{name:'Conditions d’utilisation',exact:true}).getAttribute('href'),options.terms_url)
      await page.screenshot({path:resolve(evidence,format+'-'+(path==='/'?'dashboard':path.replaceAll('/','_'))+'.png'),fullPage:true})
      results.push({format,path,passed:true,viewportWidth:layout.width,scrollWidth:layout.scrollWidth})
    }
    assert.deepEqual(errors,[])
    await context.close()
  }
  assert.deepEqual(unexpected,[])
  assert.ok(!requests.some(r=>/ui-config|deletion-status|\/download/.test(r.path)))
  await writeFile(resolve(root,baseline?'baseline-browser-results.json':'browser-results.json'),JSON.stringify({status:'passed',
    browser:browser.version(),network:'all requests intercepted; synthetic data only',
    results,requests,unexpected},null,2)+'\n')
  console.log(JSON.stringify({status:'passed',screens:results.length,browser:browser.version(),unexpected}))
}catch(error){
  await writeFile(resolve(root,baseline?'baseline-browser-results.json':'browser-results.json'),JSON.stringify({status:'failed',error:String(error),results,requests,unexpected},null,2)+'\n')
  throw error
}finally{await browser.close()}
