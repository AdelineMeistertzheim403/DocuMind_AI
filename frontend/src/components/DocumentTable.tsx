import { ArrowUpRight, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { DocumentSummary } from '../types/api'
import { formatDate, formatSize } from '../services/api'
import { useWorkspace } from './Workspace'
import { FileIcon } from './ui'

export function DocumentTable({ documents }: { documents: DocumentSummary[] }) {
  const { confirmDelete } = useWorkspace()
  return <div className="table-scroll"><table className="document-table"><thead><tr><th>Nom du document</th><th>Format</th><th>Taille</th><th>Date d’import</th><th><span className="sr-only">Actions</span></th></tr></thead>
    <tbody>{documents.map(document => <tr key={document.id}><td><Link className="document-name" to={`/documents/${document.id}`}><FileIcon pdf={document.media_type === 'application/pdf'} small/><span><strong>{document.filename}</strong><small>Texte extrait · prêt à consulter</small></span></Link></td><td><span className={`format-badge ${document.media_type === 'application/pdf' ? 'pdf' : 'txt'}`}>{document.media_type === 'application/pdf' ? 'PDF' : 'TXT'}</span></td><td className="nowrap">{formatSize(document.size_bytes)}</td><td className="nowrap">{formatDate(document.created_at)}</td><td><div className="row-actions"><Link className="icon-button" aria-label={`Ouvrir ${document.filename}`} to={`/documents/${document.id}`}><ArrowUpRight size={18}/></Link><button className="icon-button delete-action" aria-label={`Supprimer ${document.filename}`} onClick={() => confirmDelete(document)}><Trash2 size={16}/></button></div></td></tr>)}</tbody></table></div>
}
