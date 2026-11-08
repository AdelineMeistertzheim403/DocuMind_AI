// @vitest-environment-options {"url":"https://documind.test"}
import {render,screen,fireEvent,waitFor} from '@testing-library/react'
import {MemoryRouter} from 'react-router-dom'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {it,expect,vi} from 'vitest'
import {AccountAccess} from './Account'
import * as services from '../services/account'

const options:services.AccountOptions={registration_mode:'invite',application_profile:'beta_lite',
  lite_admissions_available:true,terms_version:'lite-test-v1',terms_url:'https://documind.test/terms',
  privacy_url:'https://documind.test/privacy'}
function mount(){
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>
    <MemoryRouter><AccountAccess mode="register"/></MemoryRouter></QueryClientProvider>)
}
function fill(){
  fireEvent.change(screen.getByLabelText('Email'),{target:{value:'synthetic@example.test'}})
  fireEvent.change(screen.getByLabelText('Mot de passe'),{target:{value:'Fictitious-password-123'}})
  fireEvent.change(screen.getByLabelText('Invitation'),{target:{value:'synthetic-invitation-never-real-0000000000'}})
}
it('reste fermé sans confirmation indépendante disponible',async()=>{
  vi.spyOn(services.account,'options').mockResolvedValue({...options,lite_admissions_available:false})
  mount()
  expect(await screen.findByText(/Les admissions sont fermées/)).toBeVisible()
  expect(screen.getByRole('button',{name:'Inscription'})).toBeDisabled()
})
it('exige majorité et CGU, puis affiche une attente sans persister le mot de passe',async()=>{
  vi.spyOn(services.account,'options').mockResolvedValue(options)
  const post=vi.spyOn(services,'accountPost').mockResolvedValue({profile:'beta_lite',operation_id:'operation-1',
    state:'proposal_created',created:false,confirmation_operational:false})
  mount()
  await screen.findByText(/Version des CGU : lite-test-v1/)
  expect(screen.getByLabelText(/Je déclare être majeur/)).toBeRequired()
  expect(screen.getByLabelText(/J’ai consulté/)).toBeRequired()
  fill()
  fireEvent.click(screen.getByLabelText(/Je déclare être majeur/))
  fireEvent.click(screen.getByLabelText(/J’ai consulté/))
  fireEvent.click(screen.getByRole('button',{name:'Inscription'}))
  expect(await screen.findByText(/Préparation en attente de confirmation/)).toBeVisible()
  expect(screen.getByLabelText('Mot de passe')).toHaveValue('')
  expect(screen.getByLabelText('Invitation')).toHaveValue('')
  expect(screen.queryByText(/Compte créé/)).not.toBeInTheDocument()
  expect(post).toHaveBeenCalledWith('/auth/register',expect.objectContaining({adult_declared:true,
    terms_accepted:true,terms_version:'lite-test-v1'}))
  fill()
  post.mockResolvedValue({profile:'beta_lite',operation_id:'operation-1',state:'result_pending',created:false,confirmation_operational:false})
  fireEvent.click(screen.getByRole('button',{name:'Inscription'}))
  expect(await screen.findByText(/La connexion reste fermée/)).toBeVisible()
  expect(post).toHaveBeenLastCalledWith('/auth/register',expect.objectContaining({operation_id:'operation-1'}))
  fill()
  post.mockResolvedValue({profile:'beta_lite',operation_id:'operation-1',state:'admitted',created:true,confirmation_operational:false})
  fireEvent.click(screen.getByRole('button',{name:'Inscription'}))
  await waitFor(()=>expect(screen.getByText(/Compte admis après confirmation/)).toBeVisible())
})
it('refuse une réponse qui annonce created avant confirmation',()=>{
  expect(()=>services.liteAdmissionResult({profile:'beta_lite',operation_id:'id',state:'proposal_created',
    created:true,confirmation_operational:false})).toThrow()
})
