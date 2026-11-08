import {test as base,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import {randomBytes,randomUUID} from 'node:crypto'
import {resolve} from 'node:path'

export const test=base.extend<{personalAccount:void}>({
  personalAccount:[async({page},use)=>{
    const username=`e2e-${randomUUID()}`, owner=randomUUID(),password=randomBytes(24).toString('base64url')
    const code=`import sys,json
from uuid import UUID
from sqlalchemy import select,delete
from backend.config import Settings
from backend.db import make_engine,make_sessions
from backend.auth import User,hash_password
from backend.account_models import Workspace,WorkspaceMembership
from backend.ai.models import AIBudget
from backend.models import Document
from backend.services.documents import delete_document
d=json.load(sys.stdin);settings=Settings();engine=make_engine(settings.database_url)
with make_sessions(engine)() as s:
 if d['action']=='create':
  s.add(Workspace(owner_id=UUID(d['owner'])));s.flush()
  u=User(owner_id=UUID(d['owner']),username=d['username'],password_hash=hash_password(d['password']))
  s.add(u);s.flush();s.add(WorkspaceMembership(user_id=u.id,owner_id=u.owner_id))
  s.add(AIBudget(id='byok:'+d['owner']+':openai'));s.commit()
 else:
  for doc in s.scalars(select(Document).where(Document.owner_id==UUID(d['owner']))).all():delete_document(s,settings,doc)
  s.execute(delete(User).where(User.username==d['username']))
  s.execute(delete(Workspace).where(Workspace.owner_id==UUID(d['owner'])))
  s.execute(delete(AIBudget).where(AIBudget.id=='byok:'+d['owner']+':openai'));s.commit()
engine.dispose()`
    const account=(action:string)=>execFileSync('docker',['compose','exec','-T','api','python','-c',code],{cwd:resolve('..'),input:JSON.stringify({action,username,owner,password}),stdio:['pipe','pipe','pipe']})
    account('create')
    try{
      await page.goto('/login')
      await page.getByLabel('Email ou identifiant historique').fill(username)
      await page.getByLabel('Mot de passe',{exact:true}).fill(password)
      await page.getByRole('button',{name:'Connexion',exact:true}).click()
      await expect(page.getByRole('heading',{name:'Tableau de bord'})).toBeVisible()
      await use()
    }finally{account('delete')}
  },{auto:true}],
})
export {expect}
