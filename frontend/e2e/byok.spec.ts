import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { randomBytes, randomUUID } from 'node:crypto'
import { resolve } from 'node:path'

test('BYOK HTTPS : compte, cookie sécurisé, clé éphémère et déconnexion sans appel OpenAI', async ({ browser, viewport, isMobile, hasTouch }) => {
  test.skip(process.env.BYOK_E2E !== '1', 'Nécessite le profil Docker HTTPS ; aucun appel OpenAI réel')
  const username = `test-${randomUUID()}`
  const owner = randomUUID()
  const password = randomBytes(24).toString('base64url')
  const personal = 'test-key-never-sent-to-openai-' + randomBytes(16).toString('hex')
  const code = `import sys,json
from sqlalchemy import delete
from backend.config import Settings
from backend.db import make_engine,make_sessions
from backend.auth import User,hash_password
from backend.ai.models import AIBudget
from uuid import UUID
d=json.load(sys.stdin)
engine=make_engine(Settings().database_url)
with make_sessions(engine)() as s:
 if d['action']=='create':
  s.add(User(owner_id=UUID(d['owner']),username=d['username'],password_hash=hash_password(d['password'])))
  s.add(AIBudget(id='byok:'+d['owner']+':openai'))
 else:
  s.execute(delete(User).where(User.username==d['username']))
  s.execute(delete(AIBudget).where(AIBudget.id=='byok:'+d['owner']+':openai'))
 s.commit()
engine.dispose()`
  const account = (action: string) => execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', code], {
    cwd: resolve('..'), input: JSON.stringify({ action, owner, username, password }), stdio: ['pipe', 'pipe', 'pipe'],
  })
  account('create')
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport, isMobile, hasTouch })
  const page = await context.newPage()
  const responses: Promise<string>[] = []
  page.on('response', response => { if (response.url().includes('/bff/')) responses.push(response.text().catch(() => '')) })
  try {
    await page.goto('https://localhost:8443/settings/ai')
    await page.getByLabel('Identifiant', { exact: true }).fill(username)
    await page.getByLabel('Mot de passe', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
    await expect(page.getByRole('heading', { name: `Compte : ${username}` })).toBeVisible()
    const cookie = (await context.cookies()).find(cookie => cookie.name === '__Host-documind')
    expect(cookie).toMatchObject({ secure: true, httpOnly: true, sameSite: 'Strict' })
    expect(await page.evaluate(() => document.cookie)).not.toContain('__Host-documind')
    await page.getByLabel('Clé API OpenAI', { exact: true }).fill(personal)
    await page.getByRole('button', { name: 'Connecter sans appel fournisseur' }).click()
    await expect(page.getByText(/Clé connectée, non validée/)).toBeVisible()
    await expect(page.getByLabel('Clé API OpenAI', { exact: true })).toHaveValue('')
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0)
    await page.getByRole('button', { name: 'Déconnecter la clé', exact: true }).click()
    await expect(page.getByText('Aucune clé personnelle connectée.')).toBeVisible()
    await page.getByRole('button', { name: 'Fermer la session' }).click()
    await expect(page.getByRole('button', { name: 'Se connecter', exact: true })).toBeVisible()
    expect((await Promise.all(responses)).some(body => body.includes(personal) || body.includes(password))).toBe(false)
  } finally {
    await context.close()
    account('delete')
  }
})
