import { request } from './api'
import type { AIResult } from './ai'

export interface SummaryPlan { direct:boolean;parts:number;steps:number;levels:number;root:string;summary_chars:number;pages_total:number;empty_pages:number[];maximum_usd:number;input_limit:number;overlap_chars:number }
export interface SummaryJob { id:string;document_id:string;status:'pending'|'processing'|'completed'|'partial'|'failed'|'cancelled';error_code:string|null;plan:SummaryPlan;completed_steps:number;covered_pages:number[];unprocessed_pages:number[];empty_pages:number[];cancel_requested:boolean;partials:{node_id:string;summary:string;pages:number[];source_ids:string[]}[];result:AIResult|null;updated_at:string }
const post=(body:object):RequestInit=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const longSummary={
  plan:(id:string)=>request<SummaryPlan>(`/documents/${id}/summary-plan`),
  jobs:(id:string)=>request<SummaryJob[]>(`/documents/${id}/summary-jobs`),
  get:(id:string)=>request<SummaryJob>(`/summary-jobs/${id}`),
  start:(id:string,key:string,maximum:number)=>request<SummaryJob>(`/documents/${id}/summary-jobs`,post({consent:true,idempotency_key:key,approved_maximum_usd:maximum})),
  resume:(id:string,key:string)=>request<SummaryJob>(`/summary-jobs/${id}/resume`,post({consent:true,idempotency_key:key})),
  cancel:(id:string)=>request<SummaryJob>(`/summary-jobs/${id}/cancel`,post({})),
}
