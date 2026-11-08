import {render,screen} from '@testing-library/react'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {it,expect,vi} from 'vitest'
import {RequireAccount,AccountAccess,ProfilePage} from './Account'
import {account} from '../services/account'
import {ApiError} from '../services/api'

function mount(element:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>)}
it('refuse la navigation documentaire sans session',async()=>{
  vi.spyOn(account,'me').mockRejectedValue(new ApiError(401,'Session expirée'))
  mount(<Routes><Route element={<RequireAccount/>}><Route path="/" element={<p>Texte privé</p>}/></Route><Route path="/login" element={<p>Connexion requise</p>}/></Routes>)
  expect(await screen.findByText('Connexion requise')).toBeVisible()
  expect(screen.queryByText('Texte privé')).not.toBeInTheDocument()
})
it('explique HTTPS et bloque la saisie de compte sur HTTP',async()=>{
  mount(<AccountAccess mode="login"/>)
  expect(screen.getByRole('link',{name:'Ouvrir la connexion locale sécurisée'})).toBeVisible()
  expect(screen.getByLabelText('Mot de passe')).toBeDisabled()
})
it('montre le profil historique et les paramètres de confidentialité',async()=>{
  vi.spyOn(account,'me').mockResolvedValue({id:'id',email:null,username:'historique',owner_id:'owner',workspace:'Espace personnel'})
  mount(<ProfilePage/>)
  expect(await screen.findByText(/associer votre email vérifié/)).toBeVisible()
  expect(screen.getByRole('link',{name:'Confidentialité'})).toHaveAttribute('href','/settings/privacy')
})
