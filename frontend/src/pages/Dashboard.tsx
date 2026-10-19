import { ArrowDownToLine, ArrowRight, ArrowUpRight, Files, HardDrive, Layers3, Plus, ScanText, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDocuments } from '../hooks/useDocuments'
import { DocumentTable } from '../components/DocumentTable'
import { useWorkspace } from '../components/Workspace'
import { EmptyState, ErrorState, SectionTitle, Spinner } from '../components/ui'
import { formatNumber, formatSize } from '../services/api'

export function Dashboard() {
  const query = useDocuments(0, 6)
  const { openUpload } = useWorkspace()
  const documents = query.data?.items || []
  const bytes = documents.reduce((sum, document) => sum + document.size_bytes, 0)
  const pdfs = documents.filter(document => document.media_type === 'application/pdf').length
  return <div className="page dashboard-page"><SectionTitle eyebrow="VOTRE ESPACE DOCUMENTAIRE" title="Tableau de bord"><span className="subtle-pill"><span/>Tout commence par un document</span></SectionTitle>
    <section className="hero-card"><div className="hero-copy"><span className="hero-tag"><span/>EXPLORER. COMPRENDRE. AMÉLIORER.</span><h2>Vos documents.<br/>Une vision <span>plus claire.</span></h2><p>Transformez vos PDF et textes en informations utiles.<br className="desktop-break"/> L’essentiel, à portée de lecture.</p><button className="button primary" onClick={openUpload}><Plus size={18}/>Importer un document<ArrowUpRight size={17}/></button><small><ShieldCheck size={14}/>Analyse locale · vos données restent chez vous</small></div>
      <div className="hero-art" aria-hidden="true"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="art-cross cross-one">+</div><div className="art-cross cross-two">+</div><span className="art-dot"/>
        <div className="floating-tag"><ScanText size={14}/>Une nouvelle perspective</div><div className="art-document back-document"/><div className="art-document front-document"><span className="art-doc-icon"><Layers3 size={26}/></span><span className="art-line line-long"/><span className="art-line"/><span className="art-line line-short"/><div className="art-chart"><i/><i/><i/><i/><i/></div><div className="art-footer"><span/><span/><span/></div></div><div className="art-check"><ShieldCheck size={22}/></div>
      </div>
    </section>
    {query.error ? <ErrorState error={query.error} retry={() => query.refetch()}/> : <div className="stats-grid dashboard-stats">
      <article className="stat-card"><span className="stat-icon purple"><Files size={21}/></span><div><p>Documents enregistrés</p><strong>{query.isPending ? '—' : formatNumber(query.data!.total)}</strong><small>Dans votre bibliothèque</small></div></article>
      <article className="stat-card"><span className="stat-icon cyan-bg"><ScanText size={21}/></span><div><p>Documents PDF</p><strong>{query.isPending ? '—' : `${pdfs.toLocaleString('fr-FR')}`}<span className="stat-denominator"> / {documents.length}</span></strong><small>Parmi les derniers imports</small></div></article>
      <article className="stat-card"><span className="stat-icon blue"><HardDrive size={21}/></span><div><p>Volume des fichiers récents</p><strong>{query.isPending ? '—' : formatSize(bytes)}</strong><small>{documents.length} dernier{documents.length > 1 ? 's' : ''} document{documents.length > 1 ? 's' : ''} chargé{documents.length > 1 ? 's' : ''}</small></div></article>
    </div>}
    <div className="dashboard-lower"><section className="panel recent-panel"><div className="panel-title"><div><h2>Documents récents <span className="count-badge">{documents.length}</span></h2><p>Reprenez là où votre lecture s’est arrêtée.</p></div><Link className="text-button" to="/documents">Tout voir<ArrowRight size={15}/></Link></div>
      {query.isPending ? <Spinner/> : documents.length ? <DocumentTable documents={documents}/> : !query.error && <EmptyState title="Votre bibliothèque prend vie ici" action={<button className="button secondary" onClick={openUpload}><Plus size={16}/>Ajouter mon premier document</button>}>Importez un PDF ou un TXT pour commencer à explorer son contenu.</EmptyState>}
    </section><aside className="workflow-card"><span className="eyebrow">UN PARCOURS SIMPLE</span><h3>Du fichier<br/>à l’essentiel.</h3><ol><li><span><ArrowDownToLine size={18}/></span><div><strong>Importez</strong><p>PDF ou texte, à vous de choisir.</p></div></li><li><span><ScanText size={18}/></span><div><strong>Analysez</strong><p>Donnez du relief à votre lecture.</p></div></li><li><span><Layers3 size={18}/></span><div><strong>Explorez</strong><p>Des indicateurs pour avancer.</p></div></li></ol><div className="workflow-note"><span className="tiny-dot"/>Analyse classique locale</div></aside></div>
  </div>
}
