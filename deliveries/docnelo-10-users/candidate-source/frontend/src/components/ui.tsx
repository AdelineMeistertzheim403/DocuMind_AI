import { useEffect, useRef, type ReactNode } from 'react'
import { AlertCircle, ArrowRight, FileText, FolderOpen, LoaderCircle, X } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Spinner({ label = 'Chargement…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={21}/><span>{label}</span></div>
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  return <div className="error-state" role="alert"><AlertCircle size={21}/><div><strong>Une difficulté est survenue</strong><p>{error instanceof Error ? error.message : 'Impossible de charger les données.'}</p>{retry && <button className="text-button" onClick={retry}>Réessayer <ArrowRight size={14}/></button>}</div></div>
}
export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><FolderOpen size={30}/></span><h3>{title}</h3><p>{children}</p>{action}</div>
}
export function FileIcon({ pdf, small = false }: { pdf: boolean; small?: boolean }) {
  return <span className={`file-icon ${pdf ? 'pdf' : 'txt'} ${small ? 'small' : ''}`}><FileText size={small ? 19 : 24}/><span>{pdf ? 'PDF' : 'TXT'}</span></span>
}
export function Breadcrumb({ children }: { children: ReactNode }) {
  return <nav aria-label="Fil d’Ariane" className="breadcrumb"><Link to="/documents">Documents</Link><span>/</span>{children}</nav>
}
export function Modal({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close() }, [])
  return <dialog ref={ref} aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); if (!busy) onClose() }}
    onClick={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <div className="modal-body"><div className="modal-heading"><h2 id="modal-title">{title}</h2><button className="icon-button" aria-label="Fermer" disabled={busy} onClick={onClose}><X size={20}/></button></div>{children}</div>
  </dialog>
}
export function SectionTitle({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>{children}</div>
}
