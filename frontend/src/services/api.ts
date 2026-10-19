import type { Analysis, AnalyzeOptions, DocumentDetail, DocumentList, DocumentSummary, Health } from '../types/api'

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) { super(message); this.name = 'ApiError' }
}

const fallback: Record<number, string> = {
  401: 'La clé du service doit être vérifiée côté serveur.', 404: 'Document ou analyse introuvable.',
  413: 'Le fichier dépasse la taille autorisée.', 415: 'Seuls PDF et TXT sont acceptés.',
  422: 'Document ou paramètres non valides.', 503: 'Le service est occupé ou indisponible.',
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    if (location.protocol==='https:' && !['GET','HEAD'].includes(options.method||'GET')) {
      const protection=await fetch('/bff/auth/csrf',{credentials:'same-origin',cache:'no-store'})
      if (!protection.ok) throw new ApiError(protection.status,'La protection de session est indisponible.')
      const data=await protection.json() as {csrf_token:string}
      options={...options,headers:{...Object.fromEntries(new Headers(options.headers)), 'X-CSRF-Token':data.csrf_token}}
    }
    response = await fetch(`/bff${path}`, { ...options, credentials: 'same-origin' })
  }
  catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Connexion interrompue. Vérifiez que DocuMind est démarré.')
  }
  if (!response.ok) {
    let message = fallback[response.status] || 'Une erreur est survenue. Réessayez.'
    let code: string | undefined
    try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; if (typeof data.code === 'string') code = data.code } catch { /* Non-JSON server error */ }
    throw new ApiError(response.status, message, code)
  }
  if (response.status === 204) return undefined as T
  try { return await response.json() as T } catch { throw new ApiError(502, 'La réponse du service est illisible.') }
}

export const api = {
  config: () => request<{ max_upload_bytes: number }>('/config'),
  health: () => request<Health>('/health'),
  documents: (offset = 0, limit = 12, signal?: AbortSignal) => request<DocumentList>(`/documents?offset=${offset}&limit=${limit}`, { signal }),
  document: (id: string, signal?: AbortSignal) => request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`, { signal }),
  analysis: (id: string, signal?: AbortSignal) => request<Analysis>(`/documents/${encodeURIComponent(id)}/analysis`, { signal }),
  upload: (file: File) => {
    const data = new FormData(); data.append('file', file)
    return request<DocumentSummary>('/documents', { method: 'POST', body: data })
  },
  analyze: (id: string, options: Partial<AnalyzeOptions> = {}) => request<Analysis>(`/documents/${encodeURIComponent(id)}/analyze`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options),
  }),
  remove: (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}

export function validateFile(file: File, maximum: number): string | null {
  if (!/\.(pdf|txt)$/i.test(file.name)) return 'Choisissez un fichier PDF ou TXT.'
  if (!file.size) return 'Ce fichier est vide.'
  if (file.size > maximum) return `Le fichier dépasse la limite de ${formatSize(maximum)}.`
  return null
}

export function formatSize(bytes: number) {
  return bytes < 1024 ? `${bytes} o` : bytes < 1024 * 1024 ? `${(bytes / 1024).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Ko`
    : `${(bytes / (1024 * 1024)).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mo`
}
export const formatNumber = (value: number) => value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })
export const formatDate = (date: string) => new Date(date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
