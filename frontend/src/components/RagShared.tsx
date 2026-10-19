import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { ai, usd } from '../services/ai'
import { rag, sourceUrl, type Passage } from '../services/rag'
import { ErrorState, Spinner } from './ui'

export function DocumentPicker({ selected, onChange, maximum = 10 }: {selected: string[]; onChange: (ids: string[]) => void; maximum?: number}) {
  const documents = useInfiniteQuery({queryKey:['rag-documents'],initialPageParam:0, queryFn:({pageParam})=>api.documents(pageParam,100),
    getNextPageParam:last=>last.offset+last.items.length<last.total ? last.offset+last.items.length : undefined})
  return <section className="panel rag-picker"><h2>Documents sélectionnés : {selected.length}/{maximum}</h2><p>Seuls les documents de votre espace sont proposés. {maximum===2?'L’ordre des deux sélections définit les versions A et B.':'Sélectionnez les documents à explorer ensemble.'}</p>
    {documents.isPending && <Spinner/>}{documents.error && <ErrorState error={documents.error}/>}
    <div className="rag-document-list">{documents.data?.pages.flatMap(page=>page.items).map(item=><label key={item.id} className="checkbox-field"><input type="checkbox" checked={selected.includes(item.id)} disabled={!selected.includes(item.id)&&selected.length>=maximum} onChange={event=>onChange(event.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/><span>{maximum===2 && selected.includes(item.id) ? `${selected.indexOf(item.id)===0?'A':'B'} — `:''}{item.filename}</span></label>)}</div>
    {documents.hasNextPage && <button className="button secondary" disabled={documents.isFetchingNextPage} onClick={()=>documents.fetchNextPage()}>Charger d’autres documents</button>}
    {documents.data?.pages[0].total===0 && <p>Importez d’abord un PDF ou un fichier TXT.</p>}
  </section>
}

export function RagBudget() {
  const status=useQuery({queryKey:['ai-status'],queryFn:ai.status,refetchInterval:10000,retry:false})
  const limits=useQuery({queryKey:['rag-status'],queryFn:rag.status,refetchInterval:10000,retry:false})
  return <section className="notice rag-budget"><div>{status.data && <><strong>{status.data.mode} · {usd(status.data.spent_usd)} utilisés · {usd(status.data.reserved_usd)} réservés</strong><p>Disponible : {usd(status.data.remaining_usd)}. {status.data.enabled?'IA activée.':'IA désactivée : comparaison et recherche lexicale restent possibles.'}</p></>}<Link to="/settings/ai">Compte, clé et consommation détaillée</Link></div>{limits.data && <div className="rag-quota-list">{Object.entries(limits.data.quotas).map(([name,value])=><span key={name}>{({embedding:'Lots d’indexation',search:'Recherches vectorielles',rag_question:'Questions multi-documents',comparison:'Synthèses de comparaison'} as Record<string,string>)[name]} : {value.used}/{value.limit}</span>)}</div>}<small>Les plafonds sont estimatifs et ne garantissent pas un plafond absolu de facturation OpenAI.</small></section>
}

export function PassageCard({source}: {source: Passage}) {
  return <article className="rag-passage"><div className="rag-passage-heading"><strong>{source.filename} · page {source.page_number}</strong><Link to={sourceUrl(source)}>Ouvrir le passage</Link></div><pre>{source.excerpt}</pre><small>Score RRF : {source.rrf_score.toFixed(4)} · rang lexical {source.lexical_rank ?? '—'} · rang vectoriel {source.vector_rank ?? '—'}{source.cosine_distance!==null ? ` · distance cosinus ${source.cosine_distance.toFixed(3)}`:''}. Ces valeurs ne mesurent pas la véracité.</small></article>
}
