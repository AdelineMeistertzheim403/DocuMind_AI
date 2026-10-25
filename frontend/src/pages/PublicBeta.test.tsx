// @vitest-environment-options {"url":"https://documind.test"}
import {render,screen,fireEvent,waitFor} from '@testing-library/react'
import {MemoryRouter} from 'react-router-dom'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {it,expect,vi} from 'vitest'
import {AccountAccess,PublicInformationPage} from './Account'
import * as services from '../services/account'
import * as registration from '../services/registration'

const options={registration_mode:'public' as const,public_capacity_configured:true,terms_version:'v1',
  terms_url:'https://documind.test/terms',privacy_url:'https://documind.test/privacy',legal_notice_url:'https://documind.test/legal-notice',
  operator_name:'Fictitious operator',contact_email:'contact@example.test'}
function mount(element:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>)}

it('présente le formulaire public accessible sans demander une invitation',async()=>{
  vi.spyOn(services.account,'options').mockResolvedValue(options)
  mount(<AccountAccess mode="register"/>)
  expect(await screen.findByRole('checkbox')).toBeRequired()
  expect(screen.getByLabelText('Email')).toHaveAttribute('type','email')
  expect(screen.getByLabelText('Mot de passe')).toHaveAttribute('minlength','12')
  expect(screen.queryByLabelText('Invitation')).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:'conditions d’utilisation'})).toHaveAttribute('href',options.terms_url)
})

it('soumet une preuve, le consentement et affiche un résultat générique',async()=>{
  vi.spyOn(services.account,'options').mockResolvedValue(options)
  vi.spyOn(registration,'registrationProof').mockResolvedValue({challenge:'fictitious-challenge',proof:'42'})
  const post=vi.spyOn(services,'accountPost').mockResolvedValue({})
  mount(<AccountAccess mode="register"/>)
  await screen.findByRole('checkbox')
  fireEvent.change(screen.getByLabelText('Email'),{target:{value:'fictitious@example.test'}})
  fireEvent.change(screen.getByLabelText('Mot de passe'),{target:{value:'Fictitious-password-123'}})
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button',{name:'Inscription'}))
  expect(await screen.findByRole('status')).toHaveTextContent('Si cette demande peut aboutir')
  expect(post).toHaveBeenCalledWith('/auth/register',expect.objectContaining({terms_accepted:true,terms_version:'v1',proof:'42'}))
  expect(screen.getByLabelText('Mot de passe')).toHaveValue('')
  expect(localStorage.length).toBe(0);expect(sessionStorage.length).toBe(0)
})

it('retire le jeton du fragment et exige une action et le mot de passe pour vérifier',async()=>{
  const token='A'.repeat(43)
  history.replaceState(null,'','/verify-email#token='+token)
  vi.spyOn(services.account,'options').mockResolvedValue(options)
  const post=vi.spyOn(services,'accountPost').mockResolvedValue({verified:true})
  mount(<AccountAccess mode="verify"/>)
  await waitFor(()=>expect(location.hash).toBe(''))
  expect(post).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Mot de passe'),{target:{value:'Fictitious-password-123'}})
  fireEvent.click(screen.getByRole('button',{name:'Vérifier mon adresse e-mail'}))
  expect(await screen.findByRole('status')).toHaveTextContent('Adresse vérifiée')
  expect(post).toHaveBeenCalledWith('/auth/verify-email',{token,password:'Fictitious-password-123'})
})

it('ferme la création quand la capacité est fermée et conserve les parcours existants',async()=>{
  vi.spyOn(services.account,'options').mockResolvedValue({...options,public_capacity_configured:false})
  mount(<AccountAccess mode="register"/>)
  expect(await screen.findByText(/Les nouvelles inscriptions sont fermées/)).toBeVisible()
  expect(screen.getByRole('button',{name:'Inscription'})).toBeDisabled()
  expect(screen.getByRole('link',{name:'Connexion'})).toBeVisible()
  expect(screen.getByRole('link',{name:'Renvoyer la vérification'})).toBeVisible()
})

it('conserve l’invitation et ne rend pas un lien légal non HTTPS actif',async()=>{
  vi.spyOn(services.account,'options').mockResolvedValue({...options,registration_mode:'invite',terms_url:'javascript:unsafe'})
  const result=mount(<AccountAccess mode="register"/>)
  expect(await screen.findByLabelText('Invitation')).toBeRequired()
  result.unmount()
  mount(<PublicInformationPage/>)
  expect(await screen.findByText(/Fictitious operator/)).toBeVisible()
  expect(screen.queryByRole('link',{name:'Conditions d’utilisation'})).not.toBeInTheDocument()
})
