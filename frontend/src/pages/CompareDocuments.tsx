import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { rag } from '../services/rag'
import { ai } from '../services/ai'
import { DocumentPicker, RagBudget } from '../components/RagShared'
import { ErrorState, SectionTitle, Spinner } from '../components/ui'

const labels={added:'Ajout',removed:'Suppression',modified:'Modification',moved:'Déplacement'}
export function CompareDocuments() {
  const {id}=useParams(),navigate=useNavigate(),client=useQueryClient()
  const [ids,setIds]=useState<string[]>([]),[consent,setConsent]=useState(false)
  const requestKey=useRef<string|null>(null)
  const result=useQuery({queryKey:['comparison',id],queryFn:()=>rag.comparison(id!),enabled:!!id,retry:false})
  const state=useQuery({queryKey:['ai-status'],queryFn:ai.status,retry:false})
  const create=useMutation({mutationFn:()=>rag.compare(ids[0],ids[1]),onSuccess:data=>{client.setQueryData(['comparison',data.id],data);navigate(`/comparisons/${data.id}`)}})
  const summary=useMutation({mutationFn:()=>{requestKey.current ||=crypto.randomUUID();return rag.summarize(id!,requestKey.current)},onSuccess:data=>client.setQueryData(['comparison',id],data),onSettled:()=>{client.invalidateQueries({queryKey:['ai-status']});client.invalidateQueries({queryKey:['rag-status']})}})
  const data=result.data
  const busy=create.isPending||summary.isPending
  return <div className="page rag-page"><SectionTitle eyebrow="LIRE LES ÉVOLUTIONS" title="Comparer deux documents"/><p className="page-description">La comparaison locale repère les différences. Une synthèse IA facultative les organise ensuite, à partir des seuls changements détectés.</p><RagBudget/>
    <DocumentPicker selected={ids} onChange={value=>{setIds(value);create.reset()}} maximum={2}/><button className="button primary" disabled={ids.length!==2||busy} onClick={()=>{requestKey.current=null;summary.reset();create.mutate()}}>Comparer A → B sans appel IA</button>
    {(create.isPending||(id&&result.isPending))&&<Spinner label="Comparaison des textes et références de pages…"/>}{create.error&&<ErrorState error={create.error}/>}{result.error&&<ErrorState error={result.error}/>}
    {data&&<><section className="panel settings-card"><h2>Version A : {data.filename_a}<br/>Version B : {data.filename_b}</h2><p>{data.unchanged_blocks} bloc(s) inchangé(s) · {data.changes.length} différence(s).</p><p className="notice">Les espaces et retours de ligne sont normalisés ; casse, chiffres et ponctuation restent significatifs. L’appariement des modifications et déplacements est heuristique : vérifiez les deux versions.</p>
      {data.identical&&<p role="status" className="notice">Documents identiques après normalisation de la mise en forme.</p>}
      {data.changes.map(change=><article className={`diff-change diff-${change.kind}`} key={change.id} id={change.id}><h3>{labels[change.kind]} · {change.id}</h3><div className="diff-columns">{([['Version A · avant',change.before,data.document_a],['Version B · après',change.after,data.document_b]] as const).map(([label,side,document])=><section key={label}><h4>{label}</h4>{side?<><pre>{side.text}</pre><div className="diff-pages">{side.pages.map(page=><Link key={page} to={`/documents/${document}?page=${page}#source-text`}>Page {page} · ouvrir la source</Link>)}</div></>:<p className="muted">Aucun passage de ce côté.</p>}</section>)}</div></article>)}
    </section><section className="panel settings-card"><h2>Synthèse IA des différences</h2>{!data.ai_summary&&<><p>Seules les différences détectées seront transmises à OpenAI, dans la limite de contexte. Une couverture partielle est signalée. Aucun avis juridique définitif n’est produit.</p><label className="checkbox-field"><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)} disabled={busy}/><span>J’autorise l’envoi des différences à OpenAI et sa consommation estimée.</span></label><button className="button primary" disabled={!consent||busy||!state.data?.available||location.protocol!=='https:'} onClick={()=>summary.mutate()}>Générer la synthèse des différences</button></>}
      {summary.isPending&&<Spinner label="Synthèse des changements en cours…"/>}{summary.error&&<ErrorState error={summary.error}/>}
      {data.ai_summary&&<><p className="notice">{data.summary_coverage||'Aucune génération nécessaire.'}</p>{data.ai_summary.observations.map(item=><article className="rag-observation" key={item.change_id}><h3>{item.theme}</h3><p>{item.summary}</p><p><strong>À vérifier :</strong> {item.review}</p><a href={`#${item.change_id}`}>Voir les extraits A et B · {item.change_id}</a></article>)}<ul>{data.ai_summary.limitations.map((item,index)=><li key={index}>{item}</li>)}</ul></>}
    </section></>}
  </div>
}
