import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, FileUp, ShieldCheck, UploadCloud } from 'lucide-react'
import { useUpload } from '../hooks/useDocuments'
import { api, formatSize, validateFile } from '../services/api'
import { ErrorState, FileIcon, Modal, Spinner } from './ui'

export function UploadDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: (id: string) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const config = useQuery({ queryKey: ['config'], queryFn: api.config, staleTime: Infinity })
  const upload = useUpload()
  function choose(files: FileList | null) {
    if (!files?.length || !config.data || upload.isPending) return
    upload.reset()
    if (files.length !== 1) { setError('Importez un seul document à la fois.'); setFile(null); return }
    const selected = files[0]
    const invalid = validateFile(selected, config.data.max_upload_bytes)
    setError(invalid); setFile(invalid ? null : selected)
  }
  return <Modal title="Importer un document" onClose={onClose} busy={upload.isPending}>
    <p className="muted">Ajoutez un document à votre bibliothèque. Son texte sera extrait automatiquement.</p>
    {config.isPending ? <Spinner/> : config.error ? <ErrorState error={config.error} retry={() => config.refetch()}/> : <>
      <div className={`dropzone ${dragging ? 'dragging' : ''}`} role="button" tabIndex={upload.isPending ? -1 : 0}
        aria-label="Choisir un document PDF ou TXT" aria-disabled={upload.isPending}
        onClick={() => !upload.isPending && input.current?.click()}
        onKeyDown={event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); if (!upload.isPending) input.current?.click() } }}
        onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
        onDrop={event => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files) }}>
        <span className="upload-orb"><UploadCloud size={30}/></span>
        <strong>Glissez votre document ici</strong><span>ou <u>parcourez vos fichiers</u></span>
        <small>PDF ou TXT · {formatSize(config.data!.max_upload_bytes)} maximum</small>
      </div>
      <input ref={input} className="sr-only" type="file" accept=".pdf,.txt" aria-label="Fichier à importer" disabled={upload.isPending}
        onChange={event => { choose(event.target.files); event.target.value = '' }}/>
      {file && <div className="selected-file"><FileIcon pdf={/\.pdf$/i.test(file.name)} small/><div><strong>{file.name}</strong><small>{formatSize(file.size)}</small></div><Check size={18} className="cyan"/></div>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {upload.error && <ErrorState error={upload.error}/>}
      {upload.isPending && <Spinner label="Import et extraction du texte…"/>}
      <p className="privacy-note"><ShieldCheck size={15}/> Stockage privé · aucun envoi IA automatique</p>
      <div className="modal-actions"><button className="button secondary" disabled={upload.isPending} onClick={onClose}>Annuler</button>
        <button className="button primary" disabled={!file || upload.isPending} onClick={() => file && upload.mutate(file, { onSuccess: document => onSuccess(document.id) })}><FileUp size={17}/>{upload.isPending ? 'Import en cours…' : 'Importer le document'}</button></div>
    </>}
  </Modal>
}
