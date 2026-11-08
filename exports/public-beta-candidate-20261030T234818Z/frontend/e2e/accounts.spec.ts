import {test,expect} from './account-fixture'

test('profil, securite et confidentialite restent utilisables sur tous les formats',async({page})=>{
  for(const [path,title] of [['profile','Profil'],['security','Sécurité'],['privacy','Confidentialité']]){
    await page.goto(`/settings/${path}`)
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
  }
  await expect(page.getByRole('button',{name:'Effacer les embeddings'})).toBeDisabled()
})

test('un navigateur non connecte ne peut pas lire les documents',async({browser})=>{
  const anonymous=await browser.newContext({ignoreHTTPSErrors:true})
  try{
    const page=await anonymous.newPage()
    await page.goto('https://localhost:8443/documents')
    await expect(page.getByRole('heading',{name:'Connexion',exact:true})).toBeVisible()
    expect((await page.request.get('https://localhost:8443/bff/documents')).status()).toBe(401)
  }finally{await anonymous.close()}
})
