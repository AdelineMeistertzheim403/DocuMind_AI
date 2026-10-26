import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Info, MessageCircle, Send, Sparkles } from 'lucide-react'
import { ai, usd, type AIResult } from '../services/ai'
import { ErrorState, Spinner } from './ui'
import { ApiError, formatDate, formatNumber } from '../services/api'
import {longSummary} from '../services/longSummary'
import {LongSummary} from './LongSummary'

export function AIResultCard({ result }: { result: AIResult }) {
  const content = result.content
  return <article className="ai-result"><div className="ai-result-meta"><span>{result.provider === 'mock' ? 'Simulation sans frais' : 'Généré par IA · à vérifier'}</span><span>{formatDate(result.created_at)} · {result.model}</span></div>
    {result.question && <h3 className="ai-question">{result.question}</h3>}
    {'general_summary' in content ? <><p className="ai-prose">{content.general_summary}</p>{[['Points clés', content.key_points], ['Informations importantes', content.important_information], ['Limites et informations absentes', content.limitations]].map(([title, values]) => <section key={title as string}><h4>{title}</h4><ul>{(values as string[]).map((value, index) => <li key={index}>{value}</li>)}</ul></section>)}</> : <><p className={`ai-prose ${content.insufficient_information ? 'notice' : ''}`}>{content.answer}</p>{content.insufficient_information && <small className="muted">Le contexte sélectionné ne contient pas suffisamment d’informations.</small>}</>}
    <p className="ai-coverage">{result.coverage}</p><div className="source-list">{result.sources.map((source, index) => <details key={source.chunk_id}><summary>Source {index + 1} · page {source.page_number}<span>Voir le passage</span></summary><pre>{source.excerpt}</pre><small>Passage {source.chunk_id}</small></details>)}</div>
  </article>
}

export function Assistant({ id }: { id: string }) {
  const [tab, setTab] = useState<'summary' | 'question'>('summary')
  const [consent, setConsent] = useState(false)
  const [question, setQuestion] = useState('')
  const [offset, setOffset] = useState(0)
  const client = useQueryClient()
  const summaryKey = useRef<string | null>(null)
  const questionKey = useRef<{ question: string; key: string } | null>(null)
  const status = useQuery({ queryKey: ['ai-status'], queryFn: ai.status, retry: false, refetchInterval: 30000 })
  const plan=useQuery({queryKey:['summary-plan',id],queryFn:()=>longSummary.plan(id),retry:false})
  const summaries = useQuery({ queryKey: ['ai-summaries', id], queryFn: () => ai.summaries(id), retry: false })
  const history = useQuery({ queryKey: ['ai-history', id, offset], queryFn: () => ai.history(id, offset), retry: false })
  const refreshed = async () => { await Promise.all([client.invalidateQueries({ queryKey: ['ai-status'] }), client.invalidateQueries({ queryKey: ['ai-summaries', id] }), client.invalidateQueries({ queryKey: ['ai-history', id] })]) }
  const summary = useMutation({ mutationFn: () => { summaryKey.current ||= crypto.randomUUID(); return ai.summarize(id, summaryKey.current) }, onSettled: refreshed })
  const ask = useMutation({ mutationFn: () => {
    if (questionKey.current?.question !== question.trim()) questionKey.current = { question: question.trim(), key: crypto.randomUUID() }
    return ai.ask(id, question.trim(), questionKey.current.key)
  }, onSettled: refreshed, onSuccess: () => { setQuestion(''); questionKey.current = null; setOffset(0) } })
  const available = status.data?.enabled === true && !!status.data?.available
  const busy = summary.isPending || ask.isPending
  const quotaReached = status.data && (tab === 'summary' ? status.data.summaries_used >= status.data.summary_quota : status.data.questions_used >= status.data.question_quota)
  return <section className="panel assistant-panel" id="assistant"><div className="panel-title"><div><span className="eyebrow">UN AUTRE REGARD SUR VOTRE TEXTE</span><h2><Sparkles size={20}/>Assistant IA</h2><p>Résumé de contenu et réponses documentaires, avec leurs passages sources.</p></div><Link className="text-button" to="/settings/ai">Paramètres IA</Link></div>
    {status.isPending ? <Spinner/> : status.error ? <ErrorState error={status.error} retry={() => status.refetch()}/> : status.data && <div className="ai-budget"><span>{status.data.mode === 'USER_BYOK' ? 'Votre compte OpenAI' : 'Mode démonstration propriétaire'} · {status.data.model}</span><strong>{usd(status.data.spent_usd)} / {usd(status.data.budget_usd)}</strong><small>Réservé : {usd(status.data.reserved_usd)} · Disponible : {usd(status.data.remaining_usd)}</small><small>Quotas cumulés : résumés {status.data.summaries_used}/{status.data.summary_quota} · questions {status.data.questions_used}/{status.data.question_quota} · tokens entrée/sortie {formatNumber(status.data.input_tokens)}/{formatNumber(status.data.output_tokens)}</small></div>}
    <div className="assistant-tabs" aria-label="Fonctionnalités IA"><button className={tab === 'summary' ? 'active' : ''} aria-pressed={tab === 'summary'} onClick={() => setTab('summary')}><Sparkles size={16}/>Résumé IA</button><button className={tab === 'question' ? 'active' : ''} aria-pressed={tab === 'question'} onClick={() => setTab('question')}><MessageCircle size={16}/>Questions / Réponses</button></div>
    {!available && status.data && <p className="notice"><Info size={17}/>{status.data.reason === 'disabled' ? 'L’IA est désactivée. Les fonctionnalités IA seront disponibles ultérieurement ; les analyses classiques et les historiques restent disponibles.' : status.data.reason === 'login_required' ? 'Connectez votre compte depuis les paramètres IA sur l’accès HTTPS.' : status.data.reason?.startsWith('byok_') ? 'Connectez et validez votre clé depuis les paramètres IA.' : status.data.reason === 'budget_exhausted' ? 'Le budget est épuisé. Consultez vos résultats précédents sans nouvel appel.' : 'Le fournisseur ou ses tarifs doivent être vérifiés dans la configuration serveur.'}</p>}
    {(status.data?.enabled === true && (available || status.data?.reason === 'budget_exhausted')) && <div className="ai-consent"><p>Avant de continuer : le texte du document pour un résumé, ou une sélection de passages avec votre question, sera transmis à OpenAI. Les résultats peuvent être inexacts. <strong>Ne soumettez pas de données confidentielles sans autorisation.</strong></p><label className="checkbox-field"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={busy}/><span>J’autorise cet envoi au fournisseur externe.</span></label><small>Le plafond DocuMind est une estimation applicative, pas une garantie de plafond de facturation OpenAI.</small></div>}
    {quotaReached && <p className="notice">Quota atteint. Les résultats existants restent consultables.</p>}
    {tab === 'summary' ? <div className="assistant-content">{plan.isPending?<Spinner label="Estimation du traitement sans appel IA…"/>:plan.error?<ErrorState error={plan.error} retry={()=>plan.refetch()}/>:plan.data&&!plan.data.direct?<LongSummary id={id} plan={plan.data} available={available} canResume={status.data?.enabled === true && (available || status.data?.reason === 'budget_exhausted')} consent={consent}/>:<button className="button primary" disabled={!available || !consent || busy || (!!quotaReached && !summaries.data?.total)} onClick={() => summary.mutate()}><Sparkles size={17}/>{summary.isPending ? 'Résumé en cours…' : summaries.data?.total ? 'Réutiliser le résumé existant' : 'Générer un résumé'}</button>}
      {summary.isPending && <Spinner label="Lecture et synthèse bornée du document…"/>}{summary.error && <ErrorState error={summary.error}/>}
      {summaries.isPending && <Spinner label="Lecture des résumés enregistrés…"/>}{summaries.error && <ErrorState error={summaries.error} retry={() => summaries.refetch()}/>}
      {summaries.data?.items.map(result => <AIResultCard key={result.id} result={result}/>)}{summaries.data?.total === 0 && <p className="muted ai-empty">Aucun résumé IA généré. Le résumé qualité de l’analyse classique reste un diagnostic distinct.</p>}
    </div> : <div className="assistant-content"><form onSubmit={event => { event.preventDefault(); ask.mutate() }}><label htmlFor="document-question" className="field-label">Votre question sur ce document</label><textarea id="document-question" className="text-input" minLength={3} maxLength={1000} required value={question} onChange={event => setQuestion(event.target.value)} placeholder="Quels sont les objectifs du projet ?" disabled={busy} rows={3}/><div className="question-actions"><small>{question.length}/1 000 caractères</small><button className="button primary" disabled={!available || !consent || busy || !!quotaReached || question.trim().length < 3}><Send size={16}/>Poser la question</button></div></form>
      {ask.isPending && <Spinner label="Recherche des passages et préparation de la réponse…"/>}{ask.error && <ErrorState error={ask.error}/>}
      {history.isPending && <Spinner label="Lecture de l’historique…"/>}{history.error && <ErrorState error={history.error} retry={() => history.refetch()}/>}
      {history.data?.items.map(result => <AIResultCard key={result.id} result={result}/>)}{history.data?.total === 0 && <p className="muted ai-empty">Votre historique apparaîtra ici. Chaque question est autonome ; les anciennes conversations ne sont pas envoyées au modèle.</p>}
      {history.data && history.data.total > 10 && <div className="pagination"><button className="button secondary small-button" disabled={!offset} onClick={() => setOffset(offset - 10)}><ChevronLeft size={15}/>Plus récent</button><span>{offset + 1}–{Math.min(offset + 10, history.data.total)} / {history.data.total}</span><button className="button secondary small-button" disabled={offset + 10 >= history.data.total} onClick={() => setOffset(offset + 10)}>Plus ancien<ChevronRight size={15}/></button></div>}
    </div>}
    {(summary.error instanceof ApiError && summary.error.code === 'provider_uncertain') && <p className="notice">Ne créez pas une nouvelle demande pour contourner cette réservation. Une réconciliation administrative est nécessaire.</p>}
  </section>
}
