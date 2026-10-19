import { render,screen,waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient,QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter,Route,Routes } from 'react-router-dom'
import { beforeEach,afterEach,it,expect,vi } from 'vitest'
import { IntelligentLibrary } from './IntelligentLibrary'
import { CompareDocuments } from './CompareDocuments'
import { api } from '../services/api'
import { ai,type AIStatus } from '../services/ai'
import { rag,type Comparison,type Passage } from '../services/rag'
import { document } from '../test/fixtures'

const status:AIStatus={mode:'USER_BYOK',enabled:true,available:true,reason:null,provider:'mock',model:'test',budget_usd:4,spent_usd:0,reserved_usd:0,remaining_usd:4,summary_quota:20,question_quota:100,summaries_used:0,questions_used:0,requests:0,provider_calls:0,input_tokens:0,output_tokens:0,reasoning_tokens:0,pending_requests:0,pricing_verified_on:'2026-10-19'}
const source:Passage={chunk_id:'chunk',document_id:document.id,filename:document.filename,page_number:2,start_char:20,end_char:48,excerpt:'Le budget Atlas est de 120 euros.',rrf_score:.03,lexical_rank:1,vector_rank:1,cosine_distance:.15}
const comparison:Comparison={id:'comparison',document_a:document.id,document_b:'second',filename_a:'A.txt',filename_b:'B.txt',identical:false,unchanged_blocks:2,created_at:'2026-10-19',ai_summary:null,summary_coverage:null,changes:[{id:'change-1',kind:'modified',before:{text:'Budget 120 euros.',pages:[1]},after:{text:'Budget 150 euros.',pages:[2]}}]}
beforeEach(()=>{
  vi.stubGlobal('location',{protocol:'https:'})
  vi.spyOn(api,'documents').mockResolvedValue({items:[document],total:1,offset:0,limit:100})
  vi.spyOn(ai,'status').mockResolvedValue(status)
  vi.spyOn(rag,'status').mockResolvedValue({embedding_model:'text-embedding-3-small',dimensions:1536,version:'v1',max_documents:10,max_passages:8,quotas:{embedding:{used:0,limit:500}}})
  vi.spyOn(rag,'indexStatus').mockResolvedValue([])
  vi.spyOn(rag,'comparison').mockResolvedValue(comparison)
})
afterEach(()=>vi.unstubAllGlobals())
function mount(element:React.ReactNode,path='/library'){
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><MemoryRouter initialEntries={[path]}><Routes><Route path="/library" element={element}/><Route path="/comparisons/:id" element={element}/></Routes></MemoryRouter></QueryClientProvider>)
}
it('recherche lexicale explicite, sans indexation ni question automatique, et lien précis vers la source',async()=>{
  const search=vi.spyOn(rag,'search').mockResolvedValue({passages:[source],strategy:'lexical',notice:'Score de pertinence, pas une probabilité.',cached:false})
  const index=vi.spyOn(rag,'index'),ask=vi.spyOn(rag,'ask')
  const user=userEvent.setup();mount(<IntelligentLibrary/>)
  await user.click(await screen.findByRole('checkbox',{name:document.filename}))
  await user.type(screen.getByLabelText('Recherche en langage naturel'),'budget Atlas')
  expect(index).not.toHaveBeenCalled();expect(search).not.toHaveBeenCalled();expect(ask).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button',{name:'Rechercher les passages'}))
  expect(await screen.findByText(source.excerpt)).toBeVisible()
  expect(search).toHaveBeenCalledWith([document.id],'budget Atlas',false,false,expect.any(String))
  expect(screen.getByRole('link',{name:'Ouvrir le passage'})).toHaveAttribute('href',expect.stringContaining('?page=2&start=20&end=48'))
  await user.click(screen.getByRole('checkbox',{name:/Utiliser les vecteurs/}))
  expect(screen.getByRole('button',{name:'Rechercher les passages'})).toBeDisabled()
})
it('affiche les deux versions puis exige le consentement avant la synthèse des différences',async()=>{
  const summarize=vi.spyOn(rag,'summarize').mockResolvedValue({...comparison,ai_summary:{observations:[{change_id:'change-1',theme:'Budget',summary:'Montant modifié.',review:'Vérifier les montants des deux versions.'}],limitations:['À vérifier.']},summary_coverage:'1 différence sur 1.'})
  const user=userEvent.setup();mount(<CompareDocuments/>,'/comparisons/comparison')
  expect(await screen.findByText('Budget 120 euros.')).toBeVisible()
  expect(screen.getByText('Budget 150 euros.')).toBeVisible()
  const button=screen.getByRole('button',{name:'Générer la synthèse des différences'})
  expect(button).toBeDisabled();expect(summarize).not.toHaveBeenCalled()
  await user.click(screen.getByRole('checkbox',{name:/J’autorise l’envoi des différences/}))
  await user.click(button)
  await waitFor(()=>expect(summarize).toHaveBeenCalledWith('comparison',expect.any(String)))
  expect(await screen.findByText('Montant modifié.')).toBeVisible()
  expect(screen.getByRole('link',{name:/Voir les extraits A et B/})).toHaveAttribute('href','#change-1')
})
