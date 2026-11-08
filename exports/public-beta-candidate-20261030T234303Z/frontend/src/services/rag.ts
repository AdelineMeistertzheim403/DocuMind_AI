import { request } from './api'

export interface Passage { chunk_id: string; document_id: string; filename: string; page_number: number; start_char: number; end_char: number; excerpt: string; rrf_score: number; lexical_rank: number | null; vector_rank: number | null; cosine_distance: number | null }
export interface SearchResult { passages: Passage[]; strategy: string; notice: string; cached: boolean }
export interface RagAnswer { id: string; content: { answer: string; insufficient_information: boolean; source_ids: string[] }; sources: Passage[]; strategy: string; cached: boolean }
export interface Job { id: string; document_id: string; model: string; dimensions: number; version: string; status: string; completed: number; total: number; error_code: string | null; updated_at: string }
export interface Change { id: string; kind: 'added' | 'removed' | 'modified' | 'moved'; before: { text: string; pages: number[] } | null; after: { text: string; pages: number[] } | null }
export interface Comparison { id: string; document_a: string; document_b: string; filename_a: string; filename_b: string; identical: boolean; changes: Change[]; unchanged_blocks: number; ai_summary: { observations: {change_id: string; theme: string; summary: string; review: string}[]; limitations: string[] } | null; summary_coverage: string | null; created_at: string }
export interface RagStatus { embedding_model: string; dimensions: number; version: string; max_documents: number; max_passages: number; quotas: Record<string, { used: number; limit: number }> }
const post = (body: object): RequestInit => ({ method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) })
export const rag = {
  status: () => request<RagStatus>('/search/status'),
  indexStatus: (id: string) => request<Job[]>(`/documents/${id}/index`),
  index: (id: string, force: boolean, key: string) => request<Job>(`/documents/${id}/index`, post({consent:true, force, idempotency_key:key})),
  search: (ids: string[], query: string, semantic: boolean, consent: boolean, key: string) => request<SearchResult>('/search/semantic',post({document_ids:ids, query, semantic, consent, limit:8, idempotency_key:key})),
  ask: (ids: string[], query: string, semantic: boolean, key: string) => request<RagAnswer>('/search/ask',post({document_ids:ids, query, semantic, consent:true, limit:8, idempotency_key:key})),
  compare: (a: string, b: string) => request<Comparison>('/documents/compare',post({document_a:a,document_b:b})),
  comparison: (id: string) => request<Comparison>(`/comparisons/${id}`),
  summarize: (id: string, key: string) => request<Comparison>(`/comparisons/${id}/summarize`,post({consent:true,idempotency_key:key})),
}
export const sourceUrl = (source: Passage) => `/documents/${source.document_id}?page=${source.page_number}&start=${source.start_char}&end=${source.end_char}#source-text`
