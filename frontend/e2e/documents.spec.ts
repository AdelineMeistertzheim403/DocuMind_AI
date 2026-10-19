import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

for (const format of ['txt', 'pdf'] as const) {
test(`import ${format} → texte extrait → analyse → graphiques → suppression`, async ({ page, request }) => {
  const name = `verification-${Date.now()}.${format}`
  let id: string | undefined
  const consoleErrors: string[] = []
  page.on('pageerror', error => consoleErrors.push(error.message))
  page.on('request', request => {
    if (request.headers()['x-api-key']) consoleErrors.push('API key sent by the browser')
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Tableau de bord' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  if (test.info().project.name === 'mobile') {
    await page.getByRole('button', { name: 'Ouvrir le menu' }).click()
    await page.getByRole('link', { name: 'Documents', exact: true }).click()
  } else await page.getByRole('link', { name: 'Documents', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Importer un document', exact: true }).last().click()
  const buffer = format === 'pdf' ? await readFile(new URL('./fixtures/sample.pdf', import.meta.url)) : Buffer.from('Docker utilise une API. Cette API traite des documents.')
  await page.getByLabel('Fichier à importer').setInputFiles({ name, mimeType: format === 'pdf' ? 'application/pdf' : 'text/plain', buffer })
  try {
    await page.getByRole('button', { name: 'Importer le document', exact: true }).click()
    await expect(page.getByRole('heading', { name })).toBeVisible()
    id = new URL(page.url()).pathname.split('/')[2]
    await expect(page.locator('.extracted-text')).toContainText('Docker utilise une API.')
    await page.getByRole('button', { name: 'Lancer l’analyse', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Résultats d’analyse.' })).toBeVisible()
    await expect(page.getByText('Mots analysés', { exact: true })).toBeVisible()
    await expect(page.locator('.metric-card').first()).toContainText('9')
    await page.getByRole('button', { name: 'Résumé qualité', exact: true }).click()
    await expect(page.getByText(/Il ne résume pas le sujet du document/)).toBeVisible()
    await page.getByRole('button', { name: 'Graphiques', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Score de lisibilité', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.getByRole('link', { name: 'Revoir le document' }).click()
    await page.getByRole('button', { name: 'Supprimer', exact: true }).click()
    await page.getByRole('button', { name: 'Supprimer définitivement', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible()
    await expect(page.getByText('Document supprimé.', { exact: true })).toBeVisible()
    expect(consoleErrors).toEqual([])
  } finally {
    if (id) await request.delete(`/bff/documents/${id}`)
  }
})
}

test('navigation clavier, fenêtre modale et mise en page responsive', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByRole('heading', { name: 'Tableau de bord' }).waitFor()
  if (testInfo.project.name === 'mobile') {
    const toggle = page.getByRole('button', { name: 'Ouvrir le menu' })
    await toggle.click()
    await expect(page.getByRole('dialog', { name: 'Navigation principale' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(toggle).toBeFocused()
    await expect(page.locator('.sidebar')).not.toBeVisible()
  }
  await page.getByRole('button', { name: 'Importer un document', exact: true }).last().click()
  await expect(page.getByRole('dialog', { name: 'Importer un document' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})
