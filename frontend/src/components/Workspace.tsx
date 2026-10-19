import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, Trash2, X } from 'lucide-react'
import { UploadDialog } from './UploadDialog'
import { ErrorState, Modal, Spinner } from './ui'
import { useRemove } from '../hooks/useDocuments'
import type { DocumentSummary } from '../types/api'

interface Workspace {
  openUpload: () => void; confirmDelete: (document: DocumentSummary) => void; notify: (text: string) => void
}
const Context = createContext<Workspace | null>(null)
export function useWorkspace() {
  const context = useContext(Context)
  if (!context) throw new Error('Workspace provider is missing')
  return context
}
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [upload, setUpload] = useState(false)
  const [target, setTarget] = useState<DocumentSummary | null>(null)
  const [toast, setToast] = useState('')
  const remove = useRemove()
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(''), 6000); return () => clearTimeout(timer) } }, [toast])
  return <Context.Provider value={{ openUpload: () => setUpload(true), confirmDelete: document => { remove.reset(); setTarget(document) }, notify: setToast }}>
    {children}
    {upload && <UploadDialog onClose={() => setUpload(false)} onSuccess={id => { setUpload(false); setToast('Document importé. Le texte est prêt à être analysé.'); navigate(`/documents/${id}`) }}/>}
    {target && <Modal title="Supprimer ce document ?" onClose={() => setTarget(null)} busy={remove.isPending}>
      <span className="delete-symbol"><Trash2 size={25}/></span><p>Le document <strong className="break-word">{target.filename}</strong>, son texte et ses analyses seront supprimés définitivement.</p>
      {remove.error && <ErrorState error={remove.error}/>}{remove.isPending && <Spinner label="Suppression…"/>}
      <div className="modal-actions"><button className="button secondary" disabled={remove.isPending} onClick={() => setTarget(null)}>Conserver</button>
        <button className="button danger" disabled={remove.isPending} onClick={() => remove.mutate(target.id, { onSuccess: () => {
          setTarget(null); setToast('Document supprimé.'); navigate('/documents')
        } })}>Supprimer définitivement</button></div>
    </Modal>}
    {toast && <div className="toast" role="status"><CheckCircle2 size={20}/><span>{toast}</span><button className="icon-button" aria-label="Fermer la notification" onClick={() => setToast('')}><X size={16}/></button></div>}
  </Context.Provider>
}
