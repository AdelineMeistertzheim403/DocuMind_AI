import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, CheckCircle2, Clock3, Info, Lightbulb, ScanText } from 'lucide-react'
import { useAnalysis, useDocument } from '../hooks/useDocuments'
import { Breadcrumb, EmptyState, ErrorState, Spinner } from '../components/ui'
import { AnalysisCharts, DataChart, distribution, fromRecord } from '../components/Charts'
import { ApiError, formatDate, formatNumber } from '../services/api'
import type { AnalysisResult } from '../types/api'

const tabs = [
  ['statistics', 'Statistiques'], ['quality', 'Résumé qualité'], ['readability', 'Lisibilité'],
  ['words', 'Mots fréquents'], ['sentences', 'Phrases longues'], ['terms', 'Termes techniques'],
  ['structure', 'Structure'], ['style', 'Indice de style'], ['charts', 'Graphiques'],
] as const

function Readability({ result }: { result: AnalysisResult }) {
  const data = result.lisibilite
  return <section className="panel readability-card"><div className="score-ring" style={{ '--score': `${data.score}%` } as React.CSSProperties}><div><strong>{data.score}</strong><span>/ 100</span></div></div><div><p className="eyebrow">LISIBILITÉ DU DOCUMENT</p><h2>{data.niveau}</h2><p className="muted">Un indicateur pour guider votre relecture.</p><div className="score-details"><span><strong>{formatNumber(data.moyenne_mots_phrase)}</strong> mots par phrase</span><span><strong>{formatNumber(data.pourcentage_phrases_longues)} %</strong> de phrases longues</span></div></div></section>
}
function Quality({ result }: { result: AnalysisResult }) {
  const summary = result.resume_qualite
  return <><p className="notice"><Info size={17}/>Ce résumé qualité est calculé par des règles locales. Il ne résume pas le sujet du document et n’est pas généré par une IA.</p><div className="quality-grid">{[
    { title: 'Points forts', values: summary.points_forts, icon: <CheckCircle2 size={19}/>, className: 'quality-positive' },
    { title: 'Points à améliorer', values: summary.points_a_ameliorer, icon: <ScanText size={19}/>, className: 'quality-improve' },
    { title: 'Vos prochaines étapes', values: summary.recommandations, icon: <Lightbulb size={19}/>, className: 'quality-advice' },
  ].map(section => <section className={`panel quality-panel ${section.className}`} key={section.title}><span className="quality-icon">{section.icon}</span><h3>{section.title}</h3>{section.values.length ? <ul>{section.values.map((text, i) => <li key={i}>{text}</li>)}</ul> : <p className="muted">Aucun point signalé.</p>}</section>)}</div></>
}

function AnalysisSection({ tab, result }: { tab: string; result: AnalysisResult }) {
  if (tab === 'charts') return <AnalysisCharts result={result}/>
  if (tab === 'quality') return <Quality result={result}/>
  if (tab === 'readability') return <><Readability result={result}/><div className="charts-grid"><DataChart title="Répartition des phrases" data={fromRecord(result.repartition_longueurs)}/><DataChart title="Longueur des phrases" subtitle="Nombre de phrases par longueur, en mots" data={distribution(result.longueurs_phrases)}/></div></>
  if (tab === 'words') return <div className="charts-grid"><DataChart title="Les mots qui reviennent" data={result.mots_frequents.map(([name, value]) => ({ name, value }))} horizontal/><section className="panel data-list-panel"><h2>Mots fréquents</h2><p className="muted">Après retrait des mots courants ignorés par le moteur.</p>{result.mots_frequents.length ? <ol className="ranked-list">{result.mots_frequents.map(([word, count]) => <li key={word}><span>{word}</span><strong>{formatNumber(count)} <small>occ.</small></strong></li>)}</ol> : <p className="muted">Aucun mot fréquent à afficher.</p>}</section></div>
  if (tab === 'sentences') return <><div className="section-intro"><h2>{formatNumber(result.phrases_longues.length)} phrase{result.phrases_longues.length > 1 ? 's' : ''} à relire</h2><p>Les pages correspondent aux pages physiques du document.</p></div>{result.phrases_longues.length ? <div className="sentence-list">{result.phrases_longues.map((sentence, i) => <article className="panel sentence-card" key={i}><div className="sentence-meta"><span className="subtle-pill">{sentence.page ? `Page ${sentence.page}` : 'Page non identifiée'}</span><strong>{sentence.nombre_mots} mots</strong></div><blockquote>{sentence.phrase}</blockquote><div className="chip-list">{sentence.alertes.map(alert => <span className="warning-chip" key={alert}>{alert}</span>)}</div><p className="suggestion"><Lightbulb size={16}/>{sentence.suggestion}</p><small className="muted">{sentence.nombre_virgules} virgule(s) · {sentence.nombre_parentheses} parenthèse(s){sentence.connecteurs.length ? ` · connecteurs : ${sentence.connecteurs.join(', ')}` : ''}</small></article>)}</div> : <EmptyState title="Aucune phrase longue signalée">Le texte analysé ne contient aucune phrase dépassant le seuil choisi.</EmptyState>}</>
  if (tab === 'terms') return <div className="charts-grid"><DataChart title="Termes techniques présents" data={result.termes_techniques.map(item => ({ name: item.terme, value: item.occurrences }))} horizontal/><section className="panel data-list-panel"><h2>Vocabulaire recherché</h2><p className="muted">Une correspondance avec les termes configurés, sans interprétation sémantique.</p><h3>Présents · {result.termes_techniques.length}</h3><div className="chip-list">{result.termes_techniques.map(term => <span className="success-chip" key={term.terme}>{term.terme}<strong>{term.occurrences}</strong></span>)}{!result.termes_techniques.length && <p className="muted">Aucun terme trouvé.</p>}</div><h3>Absents · {result.termes_techniques_absents.length}</h3><div className="chip-list">{result.termes_techniques_absents.map(term => <span className="neutral-chip" key={term}>{term}</span>)}{!result.termes_techniques_absents.length && <p className="muted">Aucun terme absent.</p>}</div></section></div>
  if (tab === 'structure') {
    const structure = result.structure_document
    return <><div className="stats-grid"><Metric label="Lignes textuelles" value={structure.nombre_lignes_textuelles}/><Metric label="Listes à puces" value={structure.nombre_listes_puces}/><Metric label="Éléments de liste" value={structure.nombre_elements_listes_puces}/></div><section className="panel data-list-panel"><h2>Listes identifiées</h2>{structure.listes_puces.length ? structure.listes_puces.map((list, i) => <div className="structure-list" key={i}><span className="subtle-pill">Liste {i + 1}{list.page ? ` · page ${list.page}` : ''}</span><ul>{list.elements.map((item, j) => <li key={j}>{item.texte}{item.page && <small> · p. {item.page}</small>}</li>)}</ul></div>) : <p className="muted">Aucune liste identifiée dans le texte analysé.</p>}</section></>
  }
  if (tab === 'style') {
    const style = result.indice_style_artificiel
    return <><p className="notice"><Info size={18}/>{style.note}</p><div className="charts-grid"><section className="panel style-card"><span className="eyebrow">INDICE DE STYLE POTENTIELLEMENT ARTIFICIEL</span><strong className="style-score">{style.score}<small>/ 100</small></strong><h2>Niveau {style.niveau.toLocaleLowerCase('fr')}</h2><ul>{style.signaux.map(signal => <li key={signal}>{signal}</li>)}</ul><div className="score-details"><span>Diversité lexicale<strong>{formatNumber(style.diversite_lexicale * 100)} %</strong></span><span>Régularité des phrases<strong>{formatNumber(style.regularite_phrases * 100)} %</strong></span></div></section><DataChart title="Contribution des signaux" data={fromRecord(style.details)} horizontal/></div><div className="charts-grid"><DataChart title="Connecteurs fréquents" data={fromRecord(result.connecteurs_frequents)} horizontal/><DataChart title="Formules génériques" data={fromRecord(result.formules_generiques)} horizontal/></div></>
  }
  return <><div className="stats-grid four-stats"><Metric label="Mots analysés" value={result.nombre_mots}/><Metric label="Caractères" value={result.nombre_caracteres}/><Metric label="Phrases" value={result.nombre_phrases}/><Metric label="Phrases longues" value={result.phrases_longues.length}/></div><Readability result={result}/><div className="charts-grid"><DataChart title="Répartition des phrases" subtitle="Une vue d’ensemble du rythme du texte" data={fromRecord(result.repartition_longueurs)}/><DataChart title="Mots fréquents" subtitle="Les mots les plus présents dans votre document" data={result.mots_frequents.map(([name, value]) => ({ name, value }))} horizontal/></div><Quality result={result}/></>
}
function Metric({ label, value }: { label: string; value: number }) {
  return <article className="stat-card metric-card"><p>{label}</p><strong>{formatNumber(value)}</strong><span className="metric-line"/></article>
}

export function AnalysisPage() {
  const { id = '' } = useParams()
  const document = useDocument(id)
  const query = useAnalysis(id)
  const [params, setParams] = useSearchParams()
  const requested = params.get('vue') || 'statistics'
  const tab = tabs.some(([key]) => key === requested) ? requested : 'statistics'
  if (document.isPending || query.isPending) return <div className="page"><Spinner label="Chargement de l’analyse…"/></div>
  if (document.error) return <div className="page"><ErrorState error={document.error} retry={() => document.refetch()}/><Link className="button secondary" to="/documents">Revenir aux documents</Link></div>
  if (query.error) return <div className="page"><Breadcrumb>Analyse</Breadcrumb>{query.error instanceof ApiError && query.error.status === 404 ? <EmptyState title="Votre analyse reste à écrire" action={<Link className="button primary" to={`/documents/${id}`}><ScanText size={18}/>Préparer l’analyse</Link>}>Ce document est prêt. Lancez une première analyse depuis sa fiche.</EmptyState> : <ErrorState error={query.error} retry={() => query.refetch()}/>}</div>
  const analysis = query.data
  return <div className="page analysis-page"><Breadcrumb><Link to={`/documents/${id}`}>{document.data.filename}</Link><span>/</span>Analyse</Breadcrumb><div className="page-heading"><div><p className="eyebrow">COMPRENDRE VOTRE DOCUMENT</p><h1>Résultats d’analyse<span className="heading-dot">.</span></h1><p className="page-description break-word">{document.data.filename}</p></div><Link className="button secondary" to={`/documents/${id}`}><ArrowLeft size={16}/>Revoir le document</Link></div>
    <div className="analysis-info"><span><CheckCircle2 size={15}/>Analyse terminée</span><span><Clock3 size={14}/>{formatDate(analysis.created_at)}</span><span>Moteur {analysis.engine_version}</span><span>Seuil : {analysis.parameters.limite_phrase_longue} mots</span></div>
    <details className="analysis-parameters"><summary>Paramètres utilisés pour cette analyse</summary><p>Périmètre : {analysis.parameters.mode_memoire ? 'Introduction → Conclusion' : 'texte complet'} · Titres {analysis.parameters.ignorer_titres ? 'ignorés' : 'inclus'} · Blocs non narratifs {analysis.parameters.filtrer_blocs_non_narratifs_actif ? 'filtrés' : 'inclus'}</p><p>Termes recherchés : {analysis.parameters.termes_techniques?.join(', ') || 'aucun'}</p></details>
    <nav className="analysis-tabs" aria-label="Sections des résultats">{tabs.map(([key, label]) => <button key={key} aria-current={tab === key ? 'page' : undefined} className={tab === key ? 'active' : ''} onClick={() => setParams({ vue: key })}>{label}{key === 'sentences' && <span>{analysis.result.phrases_longues.length}</span>}</button>)}</nav>
    <div className="analysis-section" key={tab}><AnalysisSection tab={tab} result={analysis.result}/></div>
    <Link className="analysis-back" to={`/documents/${id}`}>Ajuster les réglages et relancer une analyse<ArrowUpRight size={15}/></Link>
  </div>
}
