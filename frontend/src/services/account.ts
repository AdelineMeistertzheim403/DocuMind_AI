import {request} from './api'

export interface Profile { id:string; email:string|null; username:string; owner_id:string; workspace:string }
export interface SessionInfo { id:string; current:boolean; expires_at:number }
export interface AccountOptions {registration_mode:'disabled'|'invite'|'public'; public_capacity_configured?:boolean;
  application_profile?:'standard'|'beta_lite';lite_admissions_available?:boolean;
  public_registration_availability?:'available'|'closed'|'full';
  public_registration_limit?:number;public_registration_requires_approval?:boolean;
  terms_version?:string;legal_notice_url?:string;privacy_url?:string;terms_url?:string;operator_name?:string;contact_email?:string}
export const account={
  me:()=>request<Profile>('/account'),
  options:()=>request<AccountOptions>('/auth/options'),
  sessions:()=>request<{items:SessionInfo[]}>('/account/sessions'),
}
export const accountPost=(path:string,body:object)=>request<Record<string,unknown>>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})

export interface LiteAdmissionResult {
  profile:'beta_lite';operation_id:string;
  state:'proposal_created'|'reservation_pending'|'reservation_confirmed'|'sql_committed'|'result_pending'|'admitted'|'uncertain'|'cancelled'|'refused';
  created:boolean;confirmation_operational:boolean;
}

export function liteAdmissionResult(value:Record<string,unknown>):LiteAdmissionResult {
  const states=['proposal_created','reservation_pending','reservation_confirmed','sql_committed','result_pending','admitted','uncertain','cancelled','refused']
  if(value.profile!=='beta_lite'||typeof value.operation_id!=='string'||typeof value.state!=='string'
    ||!states.includes(value.state)||value.created!==(value.state==='admitted')||typeof value.confirmation_operational!=='boolean'){
    throw new Error('Réponse d’admission invalide.')
  }
  return value as unknown as LiteAdmissionResult
}
