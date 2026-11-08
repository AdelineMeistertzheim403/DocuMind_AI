import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, FileUp, FolderOpen, Plus, Search, X } from 'lucide-react'
import { useDocuments } from '../hooks/useDocuments'
import { DocumentTable } from '../components/DocumentTable'
import { useWorkspace } from '../components/Workspace'
import { EmptyState, ErrorState, SectionTitle, Spinner } from '../components/ui'
import { formatNumber } from '../services/api'

export function Documents() {
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [format, setFormat] = useState('all')
  const limit = 12
  const query = useDocuments(offset, limit)
  const { openUpload } = useWorkspace()
  useEffect(() => { if (query.data && query.data.total > 0 && offset >= query.data.total) setOffset(Math.floor((query.data.total - 1) / limit) * limit) }, [query.data, offset])
  const documents = query.data?.items || []
  const filtered = documents.filter(document => document.filename.toLocaleLowerCase('fr').includes(search.toLocaleLowerCase('fr')) && (format === 'all' || document.media_type === format))
  return <div className="page"><SectionTitle eyebrow="VOTRE BIBLIOTHÈQUE" title="Documents"><button className="button primary" onClick={openUpload}><Plus size={18}/>Importer un document</button></SectionTitle>
    <p className="page-description">Vos sources, réunies au même endroit. Consultez, analysez et faites le point.</p>
    <button className="inline-upload" onClick={openUpload}><span className="inline-upload-icon"><FileUp size={24}/></span><span><strong>Un nouveau document à explorer ?</strong><small>Importez un PDF ou un TXT depuis votre ordinateur.</small></span><span className="upload-link">Ajouter un fichier<Plus size={16}/></span></button>
    <section className="panel library-panel"><div className="library-tools"><div className="filter-tabs" aria-label="Filtrer la page par format">{[['all', 'Tous les fichiers'], ['application/pdf', 'PDF'], ['text/plain', 'TXT']].map(([value, name]) => <button key={value} aria-pressed={format === value} className={format === value ? 'active' : ''} onClick={() => setFormat(value)}>{value === 'all' && <FolderOpen size={16}/>} {name}</button>)}</div>
      <div className="search-field"><Search size={17}/><input aria-label="Rechercher dans la page chargée" placeholder="Rechercher dans cette page…" value={search} onChange={event => setSearch(event.target.value)}/>{search && <button className="icon-button" aria-label="Effacer la recherche" onClick={() => setSearch('')}><X size={14}/></button>}</div></div>
      <div className="library-caption"><span>{query.data ? `${formatNumber(query.data.total)} document${query.data.total > 1 ? 's' : ''} au total` : 'Bibliothèque'}</span><small>Recherche et filtres limités aux {documents.length} documents de cette page.</small></div>
      {query.isPending ? <Spinner label="Chargement de votre bibliothèque…"/> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()}/> : filtered.length ? <DocumentTable documents={filtered}/> : <EmptyState title={documents.length ? 'Aucun résultat dans cette page' : 'Votre premier document vous attend'} action={documents.length ? <button className="button secondary" onClick={() => { setSearch(''); setFormat('all') }}>Effacer les filtres</button> : <button className="button primary" onClick={openUpload}><Plus size={16}/>Importer un document</button>}>{documents.length ? 'Essayez un autre nom ou consultez une autre page de la bibliothèque.' : 'Ajoutez un fichier pour découvrir les informations qu’il contient.'}</EmptyState>}
      {query.data && query.data.total > 0 && <div className="pagination"><span>{offset + 1}–{Math.min(offset + limit, query.data.total)} sur {formatNumber(query.data.total)}</span><div><button className="button secondary small-button" aria-label="Page précédente" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - limit))}><ChevronLeft size={16}/>Précédent</button><span className="page-number">{Math.floor(offset / limit) + 1}</span><button className="button secondary small-button" aria-label="Page suivante" disabled={offset + limit >= query.data.total || query.isFetching} onClick={() => setOffset(offset + limit)}>Suivant<ChevronRight size={16}/></button></div></div>}
    </section>
  </div>
}
