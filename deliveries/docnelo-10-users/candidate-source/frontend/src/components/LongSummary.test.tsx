import {render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter} from 'react-router-dom'
import {it,expect,vi} from 'vitest'
import {LongSummary} from './LongSummary'
import {longSummary,type SummaryPlan,type SummaryJob} from '../services/longSummary'

const plan:SummaryPlan={direct:false,parts:16,steps:31,levels:5,root:'reduce-4-0',summary_chars:900,pages_total:53,empty_pages:[],maximum_usd:.33728,input_limit:16000,overlap_chars:200}
const job:SummaryJob={id:'job',document_id:'document',status:'processing',error_code:null,plan,completed_steps:2,covered_pages:[1,2],unprocessed_pages:[3,4],empty_pages:[],cancel_requested:false,partials:[],result:null,updated_at:'2026-10-19'}
function mount(consent=true){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><MemoryRouter><LongSummary id="document" plan={plan} available canResume consent={consent}/></MemoryRouter></QueryClientProvider>)}
it('montre le coût avant confirmation et utilise uniquement la progression persistée',async()=>{
  vi.spyOn(longSummary,'jobs').mockResolvedValue([])
  const start=vi.spyOn(longSummary,'start').mockResolvedValue(job)
  const user=userEvent.setup();mount()
  const button=screen.getByRole('button',{name:'Confirmer et lancer le résumé approfondi'})
  expect(button).toBeDisabled();expect(start).not.toHaveBeenCalled()
  expect(screen.getByText(/Réservation maximale avant traitement : 0,33728 USD/)).toBeInTheDocument()
  await user.click(screen.getByRole('checkbox',{name:/Je confirme le résumé approfondi/}))
  await user.click(button)
  await waitFor(()=>expect(start).toHaveBeenCalledWith('document',expect.any(String),plan.maximum_usd))
  expect(await screen.findByText('2/31 étapes réellement terminées')).toBeVisible()
  expect(screen.getByRole('progressbar')).toHaveAttribute('value','2')
})
it('reprend une tâche partielle sans recréer une demande de résumé',async()=>{
  vi.spyOn(longSummary,'jobs').mockResolvedValue([{...job,status:'partial',error_code:'byok_disconnected'}])
  const start=vi.spyOn(longSummary,'start'),resume=vi.spyOn(longSummary,'resume').mockResolvedValue(job)
  const user=userEvent.setup();mount()
  await user.click(await screen.findByRole('button',{name:'Reprendre les étapes restantes'}))
  await waitFor(()=>expect(resume).toHaveBeenCalledWith('job',expect.any(String)))
  expect(start).not.toHaveBeenCalled()
})

it('explique une sortie tronquée et attend une reprise explicite',async()=>{
  vi.spyOn(longSummary,'jobs').mockResolvedValue([{...job,status:'partial',error_code:'output_truncated'}])
  const resume=vi.spyOn(longSummary,'resume')
  mount()
  expect(await screen.findByText(/La réponse IA a atteint la limite de sortie/)).toBeVisible()
  expect(await screen.findByRole('button',{name:'Reprendre les étapes restantes'})).toBeEnabled()
  expect(resume).not.toHaveBeenCalled()
})
