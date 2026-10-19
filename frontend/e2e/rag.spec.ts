import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import {randomUUID,randomBytes} from 'node:crypto'
import {resolve} from 'node:path'

test('Sprint 4 HTTPS : recherche multi-documents lexicale, source et comparaison locale',async({browser,viewport,isMobile,hasTouch})=>{
  test.skip(process.env.BYOK_E2E!=='1','Nécessite le profil HTTPS, sans appel fournisseur')
  const owner=randomUUID(),username=`test-${randomUUID()}`,password=randomBytes(24).toString('base64url')
  const code=`import json,sys
from uuid import UUID
from sqlalchemy import delete
from backend.auth import User,hash_password
from backend.ai.models import AIBudget
from backend.config import Settings
from backend.db import make_engine,make_sessions
d=json.load(sys.stdin);e=make_engine(Settings().database_url)
with make_sessions(e)() as s:
 if d['action']=='create':
  s.add(User(username=d['username'],owner_id=UUID(d['owner']),password_hash=hash_password(d['password'])))
  s.add(AIBudget(id='byok:'+d['owner']+':openai'))
 else:
  s.execute(delete(User).where(User.username==d['username']))
  s.execute(delete(AIBudget).where(AIBudget.id=='byok:'+d['owner']+':openai'))
 s.commit()
e.dispose()`
  const account=(action:string)=>execFileSync('docker',['compose','exec','-T','api','python','-c',code],{cwd:resolve('..'),input:JSON.stringify({action,owner,username,password}),stdio:['pipe','pipe','pipe']})
  account('create')
  const context=await browser.newContext({ignoreHTTPSErrors:true,viewport,isMobile,hasTouch})
  const page=await context.newPage(),ids:string[]=[]
  const names=[`atlas-A-${randomUUID()}.txt`,`atlas-B-${randomUUID()}.txt`]
  try{
    await page.goto('https://localhost:8443/settings/ai')
    await page.getByLabel('Identifiant',{exact:true}).fill(username)
    await page.getByLabel('Mot de passe',{exact:true}).fill(password)
    await page.getByRole('button',{name:'Se connecter',exact:true}).click()
    await expect(page.getByRole('heading',{name:`Compte : ${username}`})).toBeVisible()
    for(const [index,name]of names.entries()){
      const response=await page.request.post('https://localhost:8443/bff/documents',{multipart:{file:{name,mimeType:'text/plain',buffer:Buffer.from(`Le budget du projet Atlas est de ${index?150:120} euros.`)}}})
      expect(response.status()).toBe(201);ids.push((await response.json()).id)
    }
    await page.goto('https://localhost:8443/library')
    for(const name of names)await page.getByRole('checkbox',{name,exact:true}).check()
    await page.getByLabel('Recherche en langage naturel').fill('budget du projet Atlas')
    await page.getByRole('button',{name:'Rechercher les passages'}).click()
    await expect(page.getByRole('heading',{name:/Passages trouvés/})).toBeVisible()
    await expect(page.locator('.rag-passage')).toHaveCount(2)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    await page.getByRole('link',{name:'Ouvrir le passage'}).first().click()
    await expect(page.locator('#source-text mark')).toContainText('Le budget du projet Atlas')
    await page.goto('https://localhost:8443/compare')
    for(const name of names)await page.getByRole('checkbox',{name,exact:true}).check()
    await page.getByRole('button',{name:'Comparer A → B sans appel IA'}).click()
    await expect(page.getByRole('heading',{name:/Modification · change-1/})).toBeVisible()
    await expect(page.locator('.diff-columns')).toContainText('120 euros')
    await expect(page.locator('.diff-columns')).toContainText('150 euros')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    await page.screenshot({path:`test-results/sprint4-${test.info().project.name}.png`,fullPage:true})
    // Estimate a long summary, but never confirm or send a generation request.
    const longFile=await page.request.post('https://localhost:8443/bff/documents',{multipart:{file:{name:'long-summary-preflight.txt',mimeType:'text/plain',buffer:Buffer.from(('Chapitre Atlas.\n\nLe budget du projet est de 120 euros. Camille est responsable.\n\n').repeat(1100))}}})
    expect(longFile.status()).toBe(201)
    const longId=(await longFile.json()).id;ids.push(longId)
    let paidPosts=0
    page.on('request',request=>{if(request.method()==='POST'&&/summary-jobs|summarize/.test(request.url()))paidPosts++})
    await page.goto(`https://localhost:8443/documents/${longId}`)
    await expect(page.getByRole('heading',{name:'Résumé approfondi',exact:true})).toBeVisible()
    await expect(page.getByText(/Réservation maximale avant traitement/)).toBeVisible()
    await expect(page.getByRole('button',{name:'Confirmer et lancer le résumé approfondi'})).toBeDisabled()
    expect(paidPosts).toBe(0)
  }finally{
    for(const id of ids)expect((await page.request.delete(`https://localhost:8443/bff/documents/${id}`)).status()).toBe(204)
    await context.close();account('delete')
  }
})
