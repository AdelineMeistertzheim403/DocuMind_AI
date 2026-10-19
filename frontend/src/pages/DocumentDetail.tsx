import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, FileText, Fingerprint, ListChecks, ScanText, Settings2, Trash2 } from 'lucide-react'
import { useAnalysis, useAnalyze, useDocument } from '../hooks/useDocuments'
import { useWorkspace } from '../components/Workspace'
import { Breadcrumb, ErrorState, FileIcon, Spinner } from '../components/ui'
import { ApiError, formatDate, formatNumber, formatSize } from '../services/api'
import { Assistant } from '../components/Assistant'

export function DocumentDetailPage() {
  const { id = '' } = useParams()
  const [sourceParams] = useSearchParams()
  const query = useDocument(id)
  const analysis = useAnalysis(id)
  const analyze = useAnalyze(id)
  const navigate = useNavigate()
  const { confirmDelete, notify } = useWorkspace()
  const [page, setPage] = useState(Math.max(0, (Number(sourceParams.get('page')) || 1) - 1))
  useEffect(() => { setPage(Math.max(0, (Number(sourceParams.get('page')) || 1) - 1)) }, [id, sourceParams])
  const [longLimit, setLongLimit] = useState(35)
  const [memory, setMemory] = useState(false)
  const [ignoreTitles, setIgnoreTitles] = useState(true)
  const [filterBlocks, setFilterBlocks] = useState(true)
  const [terms, setTerms] = useState('')
  if (query.isPending) return <div className="page"><Spinner label="Ouverture du document…"/></div>
  if (query.error) return <div className="page"><Breadcrumb>Document</Breadcrumb><ErrorState error={query.error} retry={() => query.refetch()}/><Link className="button secondary" to="/documents">Revenir aux documents</Link></div>
  const document = query.data
  const pageIndex = Math.min(page, document.pages.length - 1)
  const selected = document.pages[pageIndex]
  const sourceStart = Math.max(0, Number(sourceParams.get('start')) || 0)
  const sourceEnd = Math.min(selected?.text.length || 0, Number(sourceParams.get('end')) || 0)
  const customTerms = terms.trim() ? terms.split(/[,\n]/).map(term => term.trim()).filter(Boolean) : undefined
  return <div className="page"><Breadcrumb>{document.filename}</Breadcrumb><div className="document-heading"><FileIcon pdf={document.media_type === 'application/pdf'}/><div><span className="eyebrow">FICHE DOCUMENT</span><h1>{document.filename}</h1><p>Importé le {formatDate(document.created_at)} <span>·</span> {formatSize(document.size_bytes)}</p></div><button className="button secondary delete-text" disabled={analyze.isPending} onClick={() => confirmDelete(document)}><Trash2 size={16}/>Supprimer</button></div>
    <div className="document-meta-grid"><div><FileText size={18}/><span>Format<strong>{document.media_type === 'application/pdf' ? 'Document PDF' : 'Texte UTF-8'}</strong></span></div><div><ListChecks size={18}/><span>Pages extraites<strong>{formatNumber(document.pages.length)}</strong></span></div><div><CalendarDays size={18}/><span>Date d’import<strong>{formatDate(document.created_at)}</strong></span></div></div>
    <div className="document-detail-grid"><section className="panel text-panel"><div className="panel-title"><div><h2>Texte extrait</h2><p>Le contenu conservé, page par page.</p></div><span className="subtle-pill">Lecture seule</span></div>
      <div className="text-toolbar"><span>Page {selected?.page_number ?? '—'} sur {document.pages.length}</span><div><button className="icon-button" aria-label="Page de texte précédente" disabled={pageIndex <= 0} onClick={() => setPage(pageIndex - 1)}><ChevronLeft size={18}/></button><label className="sr-only" htmlFor="page-select">Choisir la page de texte</label><select id="page-select" value={pageIndex} onChange={event => setPage(Number(event.target.value))}>{document.pages.map((item, index) => <option key={item.id} value={index}>Page {item.page_number}</option>)}</select><button className="icon-button" aria-label="Page de texte suivante" disabled={pageIndex >= document.pages.length - 1} onClick={() => setPage(pageIndex + 1)}><ChevronRight size={18}/></button></div></div>
      <pre className="extracted-text" id="source-text">{selected?.text.trim() ? (selected.page_number===Number(sourceParams.get('page')) && sourceEnd>sourceStart ? <>{selected.text.slice(0,sourceStart)}<mark>{selected.text.slice(sourceStart,sourceEnd)}</mark>{selected.text.slice(sourceEnd)}</> : selected.text) : 'Cette page ne contient aucun texte extractible.'}</pre><div className="text-panel-footer"><Fingerprint size={14}/><span title={document.sha256}>SHA-256 : {document.sha256.slice(0, 12)}…{document.sha256.slice(-8)}</span></div>
    </section><aside className="analysis-controls panel"><div className="panel-title"><div><span className="analysis-orb"><ScanText size={22}/></span><h2>Faites parler le texte.</h2><p>Un regard structuré sur la qualité de votre document.</p></div></div>
      <form onSubmit={event => { event.preventDefault(); analyze.mutate({ limite_phrase_longue: longLimit, mode_memoire: memory, ignorer_titres: ignoreTitles, filtrer_blocs_non_narratifs_actif: filterBlocks, ...(customTerms ? { termes_techniques: customTerms } : {}) }, {
        onSuccess: () => { notify('Analyse terminée. Vos résultats sont disponibles.'); navigate(`/documents/${id}/analysis`) },
      }) }}>
        <fieldset disabled={analyze.isPending}><legend className="settings-label"><Settings2 size={16}/>Paramètres d’analyse</legend><label className="field-label" htmlFor="long-limit">Seuil des phrases longues <span>mots</span></label><input id="long-limit" className="text-input" type="number" min={5} max={500} required value={longLimit} onChange={event => setLongLimit(Number(event.target.value))}/>
          <label className="checkbox-field"><input type="checkbox" checked={memory} onChange={event => setMemory(event.target.checked)}/><span>Limiter à Introduction → Conclusion</span></label>
          <label className="checkbox-field"><input type="checkbox" checked={ignoreTitles} onChange={event => setIgnoreTitles(event.target.checked)}/><span>Ignorer les titres probables</span></label>
          <label className="checkbox-field"><input type="checkbox" checked={filterBlocks} onChange={event => setFilterBlocks(event.target.checked)}/><span>Filtrer les blocs non narratifs</span></label>
          <details className="term-settings"><summary>Personnaliser les termes techniques</summary><label className="field-label" htmlFor="custom-terms">Termes, séparés par des virgules</label><textarea id="custom-terms" className="text-input" value={terms} maxLength={10099} onChange={event => setTerms(event.target.value)} placeholder="API, Docker, base de données" rows={3}/><small>Vide : liste par défaut du moteur. 100 termes maximum, 100 caractères par terme.</small></details>
          <button className="button primary analyze-button" type="submit"><ScanText size={18}/>{analyze.isPending ? 'Analyse en cours…' : 'Lancer l’analyse'}{!analyze.isPending && <ArrowRight size={17}/>}</button>
        </fieldset>
      </form>
      {analyze.isPending && <Spinner label="Le moteur examine votre texte…"/>}{analyze.error && <ErrorState error={analyze.error}/>}
      {analysis.data && <Link className="button secondary full-width" to={`/documents/${id}/analysis`}>Voir la dernière analyse<ArrowRight size={16}/></Link>}
      {analysis.error && !(analysis.error instanceof ApiError && analysis.error.status === 404) && <ErrorState error={analysis.error} retry={() => analysis.refetch()}/>}
      <p className="analysis-disclaimer">Analyse déterministe, sans IA externe. Le texte d’origine reste conservé intégralement.</p>
    </aside></div><Assistant key={id} id={id}/>
  </div>
}
