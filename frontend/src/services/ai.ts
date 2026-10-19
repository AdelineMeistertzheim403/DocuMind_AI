import { request } from './api'

export interface AIStatus {
  mode: 'OWNER_DEMO' | 'USER_BYOK'; enabled: boolean; available: boolean; reason: string | null; provider: string; model: string;
  budget_usd: number; spent_usd: number; reserved_usd: number; remaining_usd: number;
  summary_quota: number; question_quota: number; summaries_used: number; questions_used: number;
  requests: number; provider_calls: number; input_tokens: number; output_tokens: number; reasoning_tokens: number;
  pending_requests: number; pricing_verified_on: string;
}
export interface AIResult {
  id: string; document_id: string; feature: 'summary' | 'question'; question: string | null;
  content: { general_summary: string; key_points: string[]; important_information: string[]; limitations: string[]; source_ids: string[] }
    | { answer: string; insufficient_information: boolean; source_ids: string[] };
  sources: { chunk_id: string; page_number: number; excerpt: string }[];
  model: string; provider: string; created_at: string; coverage: string; cached: boolean;
}
export interface AIHistory { items: AIResult[]; total: number; offset: number; limit: number }
export interface AIUsage { id: string; feature: string; mode: string; provider: string; model: string; input_tokens: number; output_tokens: number; reasoning_tokens: number; estimated_usd: number; created_at: string }
export interface AISettings {
  username: string; owner_id: string; mode: 'OWNER_DEMO' | 'USER_BYOK'; limit_usd: number;
  key_connected: boolean; key_validated: boolean; expires_at: number;
}
const json = (body: object, method = 'POST'): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const ai = {
  status: () => request<AIStatus>('/ai/status'),
  usage: (offset = 0) => request<{items: AIUsage[]; total: number; offset: number; limit: number}>(`/ai/usage?offset=${offset}&limit=20`),
  summaries: (id: string, offset = 0) => request<AIHistory>(`/documents/${id}/summaries?offset=${offset}&limit=10`),
  history: (id: string, offset = 0) => request<AIHistory>(`/documents/${id}/ai-history?offset=${offset}&limit=10`),
  summarize: (id: string, key: string) => request<AIResult>(`/documents/${id}/summarize`, json({ consent: true, idempotency_key: key })),
  ask: (id: string, question: string, key: string) => request<AIResult>(`/documents/${id}/ask`, json({ consent: true, question, idempotency_key: key })),
  settings: () => request<AISettings>('/ai/settings'),
  login: (username: string, password: string) => request<{ connected: boolean }>('/auth/login', json({ username, password })),
  logout: () => request('/auth/logout', json({})),
  preferences: (mode: string, limit_usd: number) => request<AISettings>('/ai/settings', json({ mode, limit_usd }, 'PUT')),
  connect: (api_key: string) => request<AISettings>('/ai/key', json({ api_key })),
  validate: () => request<AISettings>('/ai/key/validate', json({})),
  disconnect: () => request<AISettings>('/ai/key', { method: 'DELETE' }),
}
export const usd = (value: number) => `${value.toLocaleString('fr-FR', { maximumFractionDigits: 6 })} USD`
