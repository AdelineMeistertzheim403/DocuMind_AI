import {render, screen, waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'
import {beforeEach, afterEach, expect, it, vi} from 'vitest'
import {AISettingsPage} from './AISettings'
import {ai, type AIStatus, type AISettings} from '../services/ai'

const status: AIStatus = {mode:'USER_BYOK',enabled:false,available:false,reason:'disabled',provider:'mock',model:'test',budget_usd:1,spent_usd:0,reserved_usd:0,remaining_usd:1,summary_quota:20,question_quota:100,summaries_used:0,questions_used:0,requests:0,provider_calls:0,input_tokens:0,output_tokens:0,reasoning_tokens:0,pending_requests:0,pricing_verified_on:'2026-10-25'}
const settings: AISettings = {username:'fictitious-user',owner_id:'owner',mode:'USER_BYOK',limit_usd:1,key_connected:true,key_validated:true,expires_at:1793000000}
beforeEach(()=>{
  vi.stubGlobal('location',{protocol:'https:'})
  vi.spyOn(ai,'settings').mockResolvedValue(settings)
  vi.spyOn(ai,'status').mockResolvedValue(status)
  vi.spyOn(ai,'usage').mockResolvedValue({items:[],total:0,offset:0,limit:20})
})
afterEach(()=>vi.unstubAllGlobals())
function mount(){
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><AISettingsPage/></QueryClientProvider>)
}
it('refuse les actions BYOK désactivées et conserve la suppression de la clé',async()=>{
  const connect=vi.spyOn(ai,'connect'), validate=vi.spyOn(ai,'validate')
  const disconnect=vi.spyOn(ai,'disconnect').mockResolvedValue({...settings,key_connected:false,key_validated:false})
  const user=userEvent.setup();mount()
  expect(await screen.findByText(/Les fonctionnalités IA seront disponibles ultérieurement/)).toBeVisible()
  expect(await screen.findByLabelText('Clé API OpenAI')).toBeDisabled()
  const connectButton=screen.getByRole('button',{name:'Connecter sans appel fournisseur'})
  const validateButton=screen.getByRole('button',{name:'Valider l’accès au modèle'})
  expect(connectButton).toBeDisabled();expect(validateButton).toBeDisabled()
  await user.click(connectButton);await user.click(validateButton)
  expect(connect).not.toHaveBeenCalled();expect(validate).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button',{name:'Déconnecter la clé'}))
  await waitFor(()=>expect(disconnect).toHaveBeenCalledOnce())
  expect(await screen.findByText('Historique de consommation')).toBeVisible()
  expect(screen.getByRole('button',{name:'Fermer la session'})).toBeEnabled()
})
it('garde les actions fournisseur fermées si le statut ne peut pas être vérifié',async()=>{
  vi.mocked(ai.status).mockRejectedValue(new Error('Fictitious unavailable status'))
  mount()
  expect(await screen.findByLabelText('Clé API OpenAI')).toBeDisabled()
  expect(screen.getByRole('button',{name:'Valider l’accès au modèle'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'Déconnecter la clé'})).toBeEnabled()
})
it('préserve la connexion et la validation explicitement activées avec des mocks',async()=>{
  vi.mocked(ai.status).mockResolvedValue({...status,enabled:true,available:true,reason:null})
  const connect=vi.spyOn(ai,'connect').mockResolvedValue(settings)
  const validate=vi.spyOn(ai,'validate').mockResolvedValue(settings)
  const user=userEvent.setup();mount()
  const input=await screen.findByLabelText('Clé API OpenAI')
  await waitFor(()=>expect(input).toBeEnabled())
  await user.type(input,'fictitious-key-for-ui-only-12345')
  await user.click(screen.getByRole('button',{name:'Connecter sans appel fournisseur'}))
  await waitFor(()=>expect(connect).toHaveBeenCalledWith('fictitious-key-for-ui-only-12345'))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Valider l’accès au modèle'})).toBeEnabled())
  await user.click(screen.getByRole('button',{name:'Valider l’accès au modèle'}))
  await waitFor(()=>expect(validate).toHaveBeenCalledOnce())
})
