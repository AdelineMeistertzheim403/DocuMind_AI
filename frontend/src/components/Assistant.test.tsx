import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import { Assistant } from './Assistant'
import { ai, type AIResult, type AIStatus } from '../services/ai'
import { ApiError } from '../services/api'
import {longSummary} from '../services/longSummary'

const status: AIStatus = { mode:'USER_BYOK', enabled:true, available:true, reason:null, provider:'mock', model:'gpt-5.6-luna', budget_usd:4, spent_usd:0, reserved_usd:0, remaining_usd:4, summary_quota:20, question_quota:100, summaries_used:0, questions_used:0, requests:0, provider_calls:0, input_tokens:0, output_tokens:0, reasoning_tokens:0, pending_requests:0, pricing_verified_on:'2026-10-19' }
const result: AIResult = { id:'result', document_id:'document', feature:'summary', question:null, model:'gpt-5.6-luna', provider:'mock', created_at:'2026-10-19', coverage:'Document intégral : 1 passage.', cached:false,
  content:{ general_summary:'Un résumé de test.', key_points:['Un point clé'], important_information:[], limitations:['Document fictif'], source_ids:['chunk'] }, sources:[{ chunk_id:'chunk', page_number:2, excerpt:'Véritable passage de la page deux.' }] }
beforeEach(() => {
  vi.spyOn(longSummary,'plan').mockResolvedValue({direct:true,parts:1,steps:1,levels:1,root:'map-0',summary_chars:100,pages_total:1,empty_pages:[],maximum_usd:.01,input_limit:16000,overlap_chars:200})
  vi.spyOn(ai, 'status').mockResolvedValue(status)
  vi.spyOn(ai, 'summaries').mockResolvedValue({ items:[], total:0, offset:0, limit:10 })
  vi.spyOn(ai, 'history').mockResolvedValue({ items:[], total:0, offset:0, limit:10 })
})
function mount() {
  const client=new QueryClient({ defaultOptions:{queries:{retry:false},mutations:{retry:false}} })
  return render(<QueryClientProvider client={client}><MemoryRouter><Assistant id="document"/></MemoryRouter></QueryClientProvider>)
}
it('demande le consentement puis génère un résumé sourcé', async () => {
  const generate=vi.spyOn(ai,'summarize').mockImplementation(async () => {
    vi.mocked(ai.summaries).mockResolvedValue({ items:[result], total:1, offset:0, limit:10 }); return result
  })
  const user=userEvent.setup(); mount()
  const button=await screen.findByRole('button',{name:'Générer un résumé'})
  expect(button).toBeDisabled()
  await user.click(await screen.findByRole('checkbox',{name:'J’autorise cet envoi au fournisseur externe.'}))
  await user.click(button)
  await waitFor(()=>expect(generate).toHaveBeenCalledWith('document', expect.any(String)))
  expect(await screen.findByText('Un résumé de test.')).toBeInTheDocument()
  await user.click(screen.getByText(/Source 1 · page 2/))
  expect(screen.getByText('Véritable passage de la page deux.')).toBeVisible()
})
it('consulte un historique même lorsque l’IA est désactivée', async () => {
  vi.mocked(ai.status).mockResolvedValue({...status, enabled:false, available:false, reason:'disabled'})
  vi.mocked(ai.summaries).mockResolvedValue({items:[result],total:1,offset:0,limit:10})
  mount()
  expect(await screen.findByText('Un résumé de test.')).toBeInTheDocument()
  expect(await screen.findByText(/L’IA est désactivée/)).toBeInTheDocument()
})
it('affiche le budget épuisé sans autoriser une nouvelle requête', async () => {
  vi.mocked(ai.status).mockResolvedValue({...status, available:false, reason:'budget_exhausted', remaining_usd:0})
  mount()
  expect(await screen.findByText(/Le budget est épuisé/)).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Générer un résumé'})).toBeDisabled()
})
it('pose une question et affiche l’absence d’informations', async () => {
  vi.spyOn(ai,'ask').mockImplementation(async () => {
    const answer:AIResult={...result, feature:'question', question:'Quelle information manque ?', content:{answer:'Information absente.',insufficient_information:true,source_ids:[]}, sources:[]}
    vi.mocked(ai.history).mockResolvedValue({items:[answer],total:1,offset:0,limit:10});return answer
  })
  const user=userEvent.setup();mount()
  await user.click(await screen.findByRole('checkbox'))
  await user.click(screen.getByRole('button',{name:'Questions / Réponses'}))
  await user.type(screen.getByRole('textbox',{name:'Votre question sur ce document'}),'Quelle information manque ?')
  await user.click(screen.getByRole('button',{name:'Poser la question'}))
  expect(await screen.findByText('Information absente.')).toBeInTheDocument()
})
it('affiche une réservation incertaine et réutilise l’identifiant lors d’un nouvel essai', async () => {
  const generate=vi.spyOn(ai,'summarize').mockRejectedValue(new ApiError(503,'Réservation conservée','provider_uncertain'))
  const user=userEvent.setup();mount()
  await user.click(await screen.findByRole('checkbox'))
  await user.click(screen.getByRole('button',{name:'Générer un résumé'}))
  expect(await screen.findByText('Réservation conservée')).toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'Générer un résumé'}))
  await waitFor(()=>expect(generate).toHaveBeenCalledTimes(2))
  expect(generate.mock.calls[0][1]).toBe(generate.mock.calls[1][1])
})
