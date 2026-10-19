import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Search, Sparkles } from 'lucide-react'
import { rag } from '../services/rag'
import { ai } from '../services/ai'
import { DocumentPicker, PassageCard, RagBudget } from '../components/RagShared'
import { ErrorState, SectionTitle, Spinner } from '../components/ui'

function IndexControl({id, consent, available}: {id:string;consent:boolean;available:boolean}) {
  const client=useQueryClient()
  const jobs=useQuery({queryKey:['index',id],queryFn:()=>rag.indexStatus(id),refetchInterval:3000,retry:false})
  const key=useRef<string|null>(null)
  const mutation=useMutation({mutationFn:(force:boolean)=>{key.current ||= crypto.randomUUID(); return rag.index(id,force,key.current)},
    onSuccess:()=>{key.current=null;client.invalidateQueries({queryKey:['index',id]});client.invalidateQueries({queryKey:['ai-status']})}})
  const active=jobs.data?.some(job=>['queued','running'].includes(job.status))
  const names:Record<string,string>={queued:'En attente',running:'En cours',completed:'Terminée',paused:'En pause — relance explicite nécessaire',failed:'Échec'}
  return <div className="rag-index-control"><Link to={`/documents/${id}`}>Ouvrir le document</Link>{jobs.data?.map(job=><p key={job.id}><strong>{names[job.status]||job.status}</strong> · {job.completed}/{job.total} passages · {job.model} · {job.dimensions} dimensions · {job.version}{job.error_code && <span> · {job.error_code}</span>}</p>)}
    <div className="settings-actions"><button className="button secondary" disabled={!consent||!available||active||mutation.isPending} onClick={()=>mutation.mutate(false)}>Indexer / reprendre les passages manquants</button><button className="button secondary" disabled={!consent||!available||active||mutation.isPending} onClick={()=>{if(window.confirm('Recalculer les vecteurs de cette configuration ? Cette réindexation peut être facturée à nouveau.')) mutation.mutate(true)}}>Réindexer explicitement</button></div>
    {mutation.error && <ErrorState error={mutation.error}/>}{jobs.error && <ErrorState error={jobs.error}/>}
  </div>
}

export function IntelligentLibrary() {
  const [ids,setIds]=useState<string[]>([]),[query,setQuery]=useState(''),[semantic,setSemantic]=useState(false),[consent,setConsent]=useState(false)
  const client=useQueryClient()
  const state=useQuery({queryKey:['ai-status'],queryFn:ai.status,retry:false})
  const config=useQuery({queryKey:['rag-status'],queryFn:rag.status,retry:false})
  const key=useRef<{signature:string;key:string}|null>(null)
  const getKey=(operation:string)=>{const signature=JSON.stringify([operation,ids,query.trim(),semantic]);if(key.current?.signature!==signature)key.current={signature,key:crypto.randomUUID()};return key.current.key}
  const refresh=()=>{client.invalidateQueries({queryKey:['ai-status']});client.invalidateQueries({queryKey:['rag-status']})}
  const search=useMutation({mutationFn:()=>rag.search(ids,query.trim(),semantic,consent,getKey('search')),onSettled:refresh})
  const ask=useMutation({mutationFn:()=>rag.ask(ids,query.trim(),semantic,getKey('ask')),onSettled:refresh})
  const busy=search.isPending||ask.isPending
  const secure=location.protocol==='https:'
  const ready=ids.length>0 && query.trim().length>=3 && !busy && secure
  return <div className="page rag-page"><SectionTitle eyebrow="CROISER LES SOURCES" title="Bibliothèque intelligente"/><p className="page-description">Retrouvez les passages de plusieurs documents et interrogez uniquement les sources de votre espace.</p><RagBudget/>
    {!secure && <p className="notice">Connectez-vous sur <a href="https://localhost:8443/library">l’accès HTTPS</a> pour utiliser la recherche multi-documents.</p>}
    <DocumentPicker selected={ids} onChange={value=>{setIds(value);search.reset();ask.reset()}} maximum={config.data?.max_documents||10}/>
    <section className="panel settings-card"><h2>Préparer la recherche</h2><p>L’indexation transmet les textes à OpenAI, par lots facturables. Une recherche sémantique transmet aussi votre requête. Aucun envoi n’est automatique.</p><label className="checkbox-field"><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/><span>J’autorise les envois nécessaires à OpenAI, avec consommation estimée sur le compte sélectionné.</span></label><small>Les vecteurs sont conservés dans votre PostgreSQL privé. Un changement de modèle ou de dimensions exige une nouvelle indexation ; les anciennes configurations sont préservées.</small>
      {ids.map(id=><IndexControl key={id} id={id} consent={consent} available={!!state.data?.available&&secure}/>)}
    </section>
    <section className="panel settings-card"><h2>Rechercher ou poser une question</h2><form onSubmit={event=>{event.preventDefault();search.mutate()}}><label htmlFor="rag-query" className="field-label">Recherche en langage naturel</label><textarea id="rag-query" className="text-input" rows={3} minLength={3} maxLength={1000} required value={query} onChange={event=>{setQuery(event.target.value);search.reset();ask.reset()}} disabled={busy}/><label className="checkbox-field"><input type="checkbox" checked={semantic} onChange={event=>{setSemantic(event.target.checked);search.reset();ask.reset()}}/><span>Utiliser les vecteurs disponibles et la fusion hybride (appel OpenAI possible)</span></label><div className="settings-actions"><button className="button primary" disabled={!ready||(semantic&&!consent)}><Search size={16}/>Rechercher les passages</button><button type="button" className="button secondary" disabled={!ready||!consent||!state.data?.available} onClick={()=>ask.mutate()}><Sparkles size={16}/>Demander une réponse sourcée</button></div></form></section>
    {busy&&<Spinner label="Recherche des passages et préparation du résultat…"/>}{search.error&&<ErrorState error={search.error}/>}{ask.error&&<ErrorState error={ask.error}/>}
    {search.data&&<section className="panel settings-card"><h2>Passages trouvés · {search.data.strategy}</h2><p className="notice">{search.data.notice}</p>{search.data.passages.map(source=><PassageCard key={source.chunk_id} source={source}/>)}{!search.data.passages.length&&<p>Aucun passage pertinent. Essayez une autre formulation ou indexez vos documents.</p>}</section>}
    {ask.data&&<section className="panel settings-card"><h2>Réponse documentaire {ask.data.cached?'· résultat réutilisé':''}</h2><p className="ai-prose">{ask.data.content.answer}</p>{ask.data.content.insufficient_information&&<p className="notice">Informations insuffisantes dans les passages sélectionnés.</p>}<p>Réponse IA à vérifier. Les citations permettent de revenir au texte conservé.</p>{ask.data.sources.map(source=><PassageCard key={source.chunk_id} source={source}/>)}</section>}
  </div>
}
