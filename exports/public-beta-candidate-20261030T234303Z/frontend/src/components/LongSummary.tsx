import {useEffect,useRef,useState} from 'react'
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query'
import {Link} from 'react-router-dom'
import {longSummary,type SummaryPlan,type SummaryJob} from '../services/longSummary'
import {usd} from '../services/ai'
import {ErrorState,Spinner} from './ui'

export function LongSummary({id,plan,available,canResume,consent}:{id:string;plan:SummaryPlan;available:boolean;canResume:boolean;consent:boolean}){
  const client=useQueryClient(),key=useRef<string|null>(null)
  const [confirmed,setConfirmed]=useState(false)
  const jobs=useQuery({queryKey:['summary-jobs',id],queryFn:()=>longSummary.jobs(id),refetchInterval:2000,retry:false})
  const current=jobs.data?.[0]
  const done=current?.status==='completed'
  useEffect(()=>{
    if(done){client.invalidateQueries({queryKey:['ai-summaries',id]});client.invalidateQueries({queryKey:['ai-status']})}
  },[done,id,client])
  const change=(job:SummaryJob)=>{client.setQueryData<SummaryJob[]>(['summary-jobs',id],old=>[job,...(old||[]).filter(item=>item.id!==job.id)]);client.invalidateQueries({queryKey:['ai-status']})}
  const start=useMutation({mutationFn:()=>{key.current ||= crypto.randomUUID();return longSummary.start(id,key.current,plan.maximum_usd)},onSuccess:job=>{key.current=null;setConfirmed(false);change(job)}})
  const resume=useMutation({mutationFn:()=>longSummary.resume(current!.id,crypto.randomUUID()),onSuccess:change})
  const cancel=useMutation({mutationFn:()=>longSummary.cancel(current!.id),onSuccess:change})
  const busy=start.isPending||resume.isPending||cancel.isPending
  const active=current&&['pending','processing'].includes(current.status)&&current.error_code!=='session_required'
  const labels={pending:'En attente',processing:'Traitement en cours',completed:'Résumé terminé',partial:'Traitement incomplet',failed:'Échec du traitement',cancelled:'Traitement annulé'}
  const messages:Record<string,string>={output_truncated:'La réponse IA a atteint la limite de sortie avant de terminer. Les étapes validées sont conservées.',provider_refusal:'Le fournisseur a refusé cette étape. Les étapes validées sont conservées.',invalid_json:'Le fournisseur a renvoyé un JSON illisible. Les étapes validées sont conservées.',invalid_schema:'La réponse IA ne respecte pas le format demandé. Les étapes validées sont conservées.',invalid_references:'La réponse IA cite une source absente du contexte. Les étapes validées sont conservées.',provider_rate_limit:'OpenAI limite temporairement les appels. Les parties validées sont conservées.',provider_uncertain:'Un appel a pu être facturé sans réponse certaine. Une réconciliation administrative est nécessaire avant de continuer.',byok_disconnected:'La session ou la clé a expiré. Reconnectez votre clé dans les paramètres IA puis reprenez.',session_required:'Reconnectez votre compte et sa clé pour reprendre les étapes restantes.',budget_exhausted:'La réservation ou la limite d’appels ne permet plus de continuer. Les parties déjà validées restent consultables.',disabled:'L’IA a été désactivée. Les parties validées restent conservées.',invalid_output:'Le fournisseur a renvoyé une sortie ou une référence invalide. Les étapes validées sont conservées.',worker_stopped:'Le worker a été interrompu. Vous pouvez reprendre les étapes restantes.'}
  return <section className="long-summary"><h3>Résumé approfondi</h3><p>{plan.parts} parties · {plan.steps} étapes prévues · {plan.levels} niveaux · {plan.pages_total} pages, dont {plan.empty_pages.length} vide(s).</p><p className="notice"><strong>Réservation maximale avant traitement : {usd(plan.maximum_usd)}.</strong> Cette borne prudente inclut les reprises fournisseur autorisées. Le coût estimé réel est calculé à partir des tokens consommés. Les plafonds restent estimatifs.</p>
    {(!current||current.status==='cancelled')&&<><label className="checkbox-field"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)} disabled={busy}/><span>Je confirme le résumé approfondi et la réservation maximale de {usd(plan.maximum_usd)}.</span></label><button className="button primary" disabled={!available||!consent||!confirmed||busy} onClick={()=>start.mutate()}>Confirmer et lancer le résumé approfondi</button></>}
    {current&&<><div className="long-progress" role="status"><strong>{labels[current.status]}</strong><progress aria-label="Étapes de résumé terminées" max={current.plan.steps} value={current.completed_steps}/><span>{current.completed_steps}/{current.plan.steps} étapes réellement terminées</span><small>Pages entièrement traitées : {current.covered_pages.length}/{current.plan.pages_total-current.empty_pages.length} pages avec texte.</small></div>
      {current.error_code&&<p className="notice">{messages[current.error_code]||`Le traitement est arrêté (${current.error_code}). Les parties validées sont conservées.`} <Link to="/settings/ai">Paramètres IA</Link></p>}
      {current.status!=='completed'&&current.unprocessed_pages.length>0&&<p>Pages encore partiellement ou non traitées : {current.unprocessed_pages.join(', ')}.</p>}
      {current.empty_pages.length>0&&<p>Pages sans texte extractible : {current.empty_pages.join(', ')}.</p>}
      {(current.status==='partial'||current.status==='failed'||current.error_code==='session_required')&&<button className="button primary" disabled={!canResume||!consent||busy||current.error_code==='provider_uncertain'} onClick={()=>resume.mutate()}>Reprendre les étapes restantes</button>}
      {['pending','processing','partial','failed'].includes(current.status)&&<button className="button secondary" disabled={busy||current.cancel_requested} onClick={()=>cancel.mutate()}>Annuler les étapes restantes</button>}
      {current.cancel_requested&&current.status!=='cancelled'&&<p>Annulation demandée. L’appel déjà transmis doit se terminer ; aucun suivant ne sera lancé.</p>}
      {current.status==='completed'&&<p>Le résultat global et ses références sont disponibles ci-dessous.</p>}
      {current.partials.length>0&&current.status!=='completed'&&<details><summary>Consulter les {current.partials.length} résumés intermédiaires validés</summary>{current.partials.map(part=><article className="rag-passage" key={part.node_id}><h4>{part.node_id} · pages {part.pages.join(', ')}</h4><p>{part.summary}</p><small>Passages sources : {part.source_ids.join(', ')}</small>{part.pages.map(page=><Link className="text-button" key={page} to={`/documents/${id}?page=${page}#source-text`}>Page {page}</Link>)}</article>)}</details>}
    </>}
    {busy&&<Spinner label="Enregistrement de la demande…"/>}{active&&<p>Vous pouvez quitter cette fiche. La progression provient des étapes enregistrées par le worker.</p>}{[start.error,resume.error,cancel.error,jobs.error].filter(Boolean).map((error,index)=><ErrorState key={index} error={error}/>)}
  </section>
}
