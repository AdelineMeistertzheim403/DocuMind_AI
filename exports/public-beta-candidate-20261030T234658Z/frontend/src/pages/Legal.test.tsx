// @vitest-environment-options {"url":"https://documind.test"}
import {render,screen,fireEvent,within} from '@testing-library/react'
import {MemoryRouter} from 'react-router-dom'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {it,expect,vi} from 'vitest'
import {AppRoutes} from '../App'
import {account,accountPost} from '../services/account'
import * as accountService from '../services/account'
import {api,ApiError} from '../services/api'
import {Layout} from '../components/Layout'
import {WorkspaceProvider} from '../components/Workspace'
import {TERMS_VERSION,termsArchive} from '../legal/documents'

function mount(path:string){
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})}><MemoryRouter initialEntries={[path]}><AppRoutes/></MemoryRouter></QueryClientProvider>)
}

it.each([
  ['/mentions-legales','Mentions légales'],['/confidentialite','Politique de confidentialité'],
  ['/cgu','Conditions générales d’utilisation'],[`/cgu/versions/${TERMS_VERSION}`,'Conditions générales d’utilisation'],
])('rend %s sans session ni API',async(path,title)=>{
  const me=vi.spyOn(account,'me').mockRejectedValue(new ApiError(401,'Non authentifié'))
  const options=vi.spyOn(account,'options').mockRejectedValue(new Error('API indisponible'))
  mount(path)
  expect(screen.getByRole('heading',{level:1,name:title})).toBeVisible()
  expect(screen.getByRole('note')).toHaveTextContent('Brouillon non approuvé')
  expect(me).not.toHaveBeenCalled();expect(options).not.toHaveBeenCalled()
  expect(screen.getByRole('link',{name:'Mentions légales (brouillon)'})).toHaveAttribute('href','/mentions-legales')
})

it('conserve une version explicite et son lien permanent sans substitution silencieuse',()=>{
  mount('/cgu')
  expect(termsArchive[TERMS_VERSION].version).toBe('beta-2026-10-v1')
  expect(screen.getByRole('link',{name:'Lien permanent de cette version'})).toHaveAttribute('href',`/cgu/versions/${TERMS_VERSION}`)
  fireEvent.click(screen.getByRole('link',{name:'Lien permanent de cette version'}))
  expect(screen.getByRole('heading',{level:1})).toHaveTextContent('Conditions générales')
})

it('conserve le texte du brouillon antérieur à son URL de version',()=>{
  mount('/cgu/versions/beta-2026-10-26-draft-1')
  expect(screen.getByRole('heading',{name:'Objet de la bêta'})).toBeVisible()
  expect(screen.queryByRole('heading',{name:'Article 1 — Objet'})).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Lien permanent de cette version'})).toHaveAttribute('href','/cgu/versions/beta-2026-10-26-draft-1')
})

it.each(['inconnue','constructor','__proto__'])('refuse la version %s sans afficher les CGU courantes à sa place',(version)=>{
  mount(`/cgu/versions/${version}`)
  expect(screen.getByRole('heading',{level:1})).toHaveTextContent('Version des CGU introuvable')
  expect(screen.queryByRole('heading',{name:'Objet de la bêta'})).not.toBeInTheDocument()
})

it('permet la navigation depuis le portail juridique malgré une panne API',async()=>{
  vi.spyOn(account,'options').mockRejectedValue(new ApiError(503,'Indisponible'))
  mount('/legal')
  expect(await screen.findByRole('status')).toHaveTextContent('brouillons locaux restent consultables')
  fireEvent.click(screen.getByRole('link',{name:'Confidentialité (brouillon)'}))
  expect(screen.getByRole('heading',{level:1})).toHaveTextContent('Politique de confidentialité')
})

it('garde les liens locaux sur le formulaire indisponible sans autoriser une inscription',async()=>{
  vi.spyOn(account,'options').mockRejectedValue(new ApiError(503,'Indisponible'))
  const post=vi.spyOn(accountService,'accountPost').mockImplementation(accountPost)
  mount('/register')
  await screen.findByRole('alert')
  expect(screen.getByRole('button',{name:'Inscription'})).toBeDisabled()
  expect(screen.getByRole('link',{name:'CGU (brouillon)'})).toHaveAttribute('href','/cgu')
  expect(post).not.toHaveBeenCalled()
})

it('affiche les liens permanents dans le footer connecté et décrit le stockage serveur',()=>{
  vi.spyOn(api,'health').mockResolvedValue({status:'ok',database:'ok'})
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><WorkspaceProvider><Layout/></WorkspaceProvider></MemoryRouter></QueryClientProvider>)
  const footer=screen.getByRole('contentinfo')
  expect(within(footer).getByRole('link',{name:'CGU (brouillon)'})).toHaveAttribute('href','/cgu')
  expect(screen.getByText(/sur le serveur du service/)).toBeVisible()
  expect(screen.queryByText('Vos documents restent dans votre environnement local.')).not.toBeInTheDocument()
})
