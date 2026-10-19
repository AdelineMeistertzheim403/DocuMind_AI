import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { KeyRound, LockKeyhole, LogOut, ShieldCheck, Unplug } from 'lucide-react'
import { ai, usd, type AISettings as Settings } from '../services/ai'
import { ErrorState, SectionTitle, Spinner } from '../components/ui'
import { formatDate } from '../services/api'

export function AISettingsPage() {
  const secure = location.protocol === 'https:'
  const settings = useQuery({ queryKey: ['ai-settings'], queryFn: ai.settings, retry: false })
  const consumption = useQuery({ queryKey: ['ai-status'], queryFn: ai.status, retry: false })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [message, setMessage] = useState('')
  const [limit, setLimit] = useState<string | null>(null)
  const [mode, setMode] = useState<Settings['mode'] | null>(null)
  const [offset, setOffset] = useState(0)
  const usage = useQuery({ queryKey: ['ai-usage', offset], queryFn: () => ai.usage(offset), enabled: !!settings.data, retry: false })
  async function action(operation: () => Promise<unknown>, text: string) {
    setBusy(true); setError(null); setMessage('')
    try { await operation(); setMessage(text); await Promise.all([settings.refetch(), consumption.refetch()]) }
    catch (failure) { setError(failure) }
    finally { setBusy(false) }
  }
  async function login(event: FormEvent) {
    event.preventDefault()
    const entered = password; setPassword('')
    await action(async () => { await ai.login(username, entered); window.location.reload() }, 'Compte connecté.')
  }
  const data = settings.data
  return <div className="page ai-settings-page"><SectionTitle eyebrow="CONNEXION ET CONSOMMATION" title="Paramètres IA"/>
    <p className="page-description">Choisissez le compte OpenAI qui finance vos traitements. La clé n’est pas votre identité DocuMind.</p>
    {!secure && <p className="notice"><LockKeyhole size={18}/>La connexion de comptes et de clés nécessite HTTPS. Lancez le profil HTTPS documenté, puis ouvrez <a href="https://localhost:8443/settings/ai">https://localhost:8443/settings/ai</a>. Ne saisissez aucune clé sur cette page HTTP.</p>}
    {settings.isPending ? <Spinner/> : !data ? <section className="panel settings-card"><h2><ShieldCheck size={21}/>Connecter votre compte DocuMind</h2><p>Le compte doit être créé par l’administrateur local. Aucun appel OpenAI n’est effectué à la connexion.</p><form onSubmit={login}><label className="field-label" htmlFor="login-name">Identifiant</label><input id="login-name" className="text-input" autoComplete="username" required maxLength={80} value={username} onChange={event => setUsername(event.target.value)} disabled={!secure || busy}/><label className="field-label" htmlFor="login-password">Mot de passe</label><input id="login-password" className="text-input" type="password" autoComplete="current-password" required minLength={12} maxLength={256} value={password} onChange={event => setPassword(event.target.value)} disabled={!secure || busy}/><button className="button primary" disabled={!secure || busy}>Se connecter</button></form><small>Session de 30 minutes par défaut, sans prolongation automatique. Un redémarrage du backend déconnecte les sessions.</small></section> : <>
      <section className="panel settings-card"><div className="settings-heading"><h2>Compte : {data.username}</h2><button className="button secondary" disabled={busy} onClick={() => action(async () => { await ai.logout(); window.location.reload() }, 'Déconnecté.')}><LogOut size={16}/>Fermer la session</button></div><p>Expiration : {new Date(data.expires_at * 1000).toLocaleTimeString('fr-FR')}. Les clés personnelles ne sont pas enregistrées en base.</p><form onSubmit={event => { event.preventDefault(); action(() => ai.preferences(mode || data.mode, Number(limit ?? data.limit_usd)), 'Mode et plafond enregistrés.') }}><label className="field-label" htmlFor="ai-mode">Mode de financement</label><select id="ai-mode" className="text-input" value={mode || data.mode} onChange={event => setMode(event.target.value as Settings['mode'])} disabled={busy}><option value="USER_BYOK">USER_BYOK — mon compte OpenAI</option><option value="OWNER_DEMO">OWNER_DEMO — démonstration du propriétaire</option></select><label className="field-label" htmlFor="ai-limit">Mon plafond applicatif BYOK (USD cumulés)</label><input id="ai-limit" type="number" className="text-input" min={0} max={100} step="0.01" required value={limit ?? data.limit_usd} onChange={event => setLimit(event.target.value)} disabled={busy}/><button className="button primary" disabled={busy}>Enregistrer les préférences</button></form><small>Ce plafond ne concerne que les appels BYOK réalisés dans DocuMind. Un changement de clé ou une nouvelle session ne remet pas les compteurs à zéro.</small></section>
      <section className="panel settings-card"><h2><KeyRound size={21}/>Ma clé OpenAI éphémère</h2><p>{data.key_connected ? data.key_validated ? 'Clé connectée et accès au modèle validé.' : 'Clé connectée, non validée. Aucun traitement n’utilisera cette clé avant validation.' : 'Aucune clé personnelle connectée.'}</p><form onSubmit={event => { event.preventDefault(); const entered = key; setKey(''); action(() => ai.connect(entered), 'Clé conservée temporairement en session. Validez son accès avant utilisation.') }}><label htmlFor="openai-key" className="field-label">Clé API OpenAI</label><input id="openai-key" className="text-input" type="password" autoComplete="off" spellCheck={false} minLength={20} maxLength={256} required value={key} onChange={event => setKey(event.target.value)} disabled={busy} placeholder="Saisir une clé personnelle"/><button className="button primary" disabled={busy || key.length < 20}>Connecter sans appel fournisseur</button></form><div className="settings-actions"><button className="button secondary" disabled={busy || !data.key_connected} onClick={() => action(ai.validate, 'Accès au modèle validé, sans génération de texte.')}>Valider l’accès au modèle</button><button className="button secondary" disabled={busy || !data.key_connected} onClick={() => action(ai.disconnect, 'Clés personnelles déconnectées des sessions de ce compte.')}><Unplug size={16}/>Déconnecter la clé</button></div><p className="notice">Le bouton de validation contacte explicitement OpenAI pour vérifier l’accès au modèle. Il ne génère aucun texte et ne transmet aucun document.</p></section>
    </>}
    {busy && <Spinner label="Mise à jour en cours…"/>}{error != null && <ErrorState error={error}/>}{message && <p role="status" className="notice">{message}</p>}
    {consumption.data && <section className="panel settings-card"><h2>Consommation DocuMind</h2><div className="ai-budget"><span>{consumption.data.mode === 'USER_BYOK' ? 'Plafond personnel BYOK' : 'Budget global de démonstration'}</span><strong>{usd(consumption.data.spent_usd)} utilisés · {usd(consumption.data.reserved_usd)} réservés</strong><span>Disponible : {usd(consumption.data.remaining_usd)}</span><small>{consumption.data.input_tokens} tokens d’entrée · {consumption.data.output_tokens} de sortie, dont {consumption.data.reasoning_tokens} de raisonnement · {consumption.data.provider_calls} appel(s) fournisseur connu(s)</small></div><p className="notice">Les montants sont des estimations prudentes, pas un plafond absolu de facturation OpenAI. Les autres applications utilisant votre clé ne sont pas comptabilisées ici.</p></section>}
    {usage.data && <section className="panel settings-card"><h2>Historique de consommation</h2>{usage.data.items.length ? <><div className="table-scroll"><table className="document-table"><thead><tr><th>Date / modèle</th><th>Mode</th><th>Tokens entrée / sortie</th><th>Coût estimé</th></tr></thead><tbody>{usage.data.items.map(item => <tr key={item.id}><td>{formatDate(item.created_at)}<br/>{item.model} · {item.feature}</td><td>{item.mode}</td><td>{item.input_tokens} / {item.output_tokens}<br/>{item.reasoning_tokens} raisonnement</td><td>{usd(item.estimated_usd)}</td></tr>)}</tbody></table></div><div className="pagination"><button className="button secondary" disabled={offset === 0} onClick={() => setOffset(offset - 20)}>Précédent</button><span>{offset + 1}–{Math.min(offset + 20, usage.data.total)} / {usage.data.total}</span><button className="button secondary" disabled={offset + 20 >= usage.data.total} onClick={() => setOffset(offset + 20)}>Suivant</button></div></> : <p>Aucun appel fournisseur comptabilisé dans ce compte.</p>}</section>}
    <p className="notice"><ShieldCheck size={18}/>Déconnecter la clé empêche les nouveaux appels de ces sessions, mais ne révoque pas la clé chez OpenAI et n’annule pas une requête déjà envoyée. Révoquez-la aussi dans votre projet OpenAI si nécessaire.</p>
  </div>
}
