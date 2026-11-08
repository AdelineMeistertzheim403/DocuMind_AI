import {LegalNavigation} from '../pages/Legal'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, BookOpen, ChevronRight, CircleHelp, FileStack, FolderOpen, LayoutDashboard, Menu, Plus, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api } from '../services/api'
import { useWorkspace } from './Workspace'
import { Modal } from './ui'

export function Layout() {
  const { openUpload } = useWorkspace()
  const [menu, setMenu] = useState(false)
  const [guide, setGuide] = useState(false)
  const sidebar = useRef<HTMLElement>(null)
  const location = useLocation()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30000, retry: false })
  useEffect(() => {
    if (!menu) return
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sidebar.current?.querySelector<HTMLButtonElement>('.mobile-close')?.focus()
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); setMenu(false) }
      if (event.key !== 'Tab') return
      const items = [...(sidebar.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)') || [])]
      const first = items[0], last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    function resized() { if (innerWidth > 720) setMenu(false) }
    window.addEventListener('keydown', keydown); window.addEventListener('resize', resized)
    return () => { document.body.style.overflow = overflow; window.removeEventListener('keydown', keydown); window.removeEventListener('resize', resized); previous?.focus() }
  }, [menu])
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Aller au contenu</a>
    {menu && <button className="sidebar-backdrop" aria-label="Fermer la navigation" onClick={() => setMenu(false)}/>}
    <aside ref={sidebar} className={`sidebar ${menu ? 'is-open' : ''}`} aria-label="Navigation principale" role={menu ? 'dialog' : undefined} aria-modal={menu || undefined}>
      <NavLink to="/" className="brand" onClick={() => setMenu(false)}><span className="brand-symbol"><BookOpen size={23}/></span><span>DocuMind<span className="brand-ai">AI</span></span></NavLink>
      <button className="icon-button mobile-close" aria-label="Fermer le menu" onClick={() => setMenu(false)}><X size={20}/></button>
      <button className="button primary sidebar-import" onClick={() => { setMenu(false); openUpload() }}><Plus size={18}/>Importer un document</button>
      <p className="nav-caption">ESPACE DE TRAVAIL</p>
      <nav className="nav-list"><NavLink to="/" end onClick={() => setMenu(false)}><LayoutDashboard size={19}/>Tableau de bord</NavLink>
        <NavLink to="/documents" onClick={() => setMenu(false)}><FolderOpen size={20}/>Documents</NavLink>
        <NavLink to="/library" onClick={() => setMenu(false)}><BookOpen size={19}/>Bibliothèque intelligente</NavLink>
        <NavLink to="/compare" onClick={() => setMenu(false)}><FileStack size={19}/>Comparer deux documents</NavLink>
        <NavLink to="/settings/ai" onClick={() => setMenu(false)}><Sparkles size={19}/>Paramètres IA</NavLink>
        <NavLink to="/settings/profile" onClick={() => setMenu(false)}><ShieldCheck size={19}/>Mon profil</NavLink>
        <NavLink to="/settings/security" onClick={() => setMenu(false)}><ShieldCheck size={19}/>Sécurité</NavLink>
        <NavLink to="/settings/privacy" onClick={() => setMenu(false)}><ShieldCheck size={19}/>Confidentialité</NavLink></nav>
      <div className="sidebar-bottom"><div className="local-card"><span className="local-card-icon"><ShieldCheck size={19}/></span><strong>Votre espace, vos données.</strong><p>Vos documents sont conservés sur le serveur du service dans un espace privé.</p><span className="local-label"><span/>Stockage privé</span></div>
        <button className="help-link" onClick={() => { setMenu(false); setGuide(true) }}><CircleHelp size={18}/>Prise en main<ArrowUpRight size={15}/></button>
        <div className="workspace-profile"><span className="avatar">DM</span><div><strong>Espace personnel</strong><small>Stockage serveur privé</small></div></div>
      </div>
    </aside>
    <div className="main-shell" inert={menu}><header className="topbar"><div className="topbar-path"><button className="icon-button mobile-menu" aria-label="Ouvrir le menu" aria-expanded={menu} onClick={() => setMenu(true)}><Menu size={22}/></button><FileStack size={17}/><span>Mon espace</span><ChevronRight size={14}/><strong>{location.pathname === '/' ? 'Vue d’ensemble' : 'Documents'}</strong></div>
      <div className={`connection-badge ${health.data ? 'online' : health.error ? 'offline' : ''}`} title={health.error ? 'Le service ne répond pas' : 'État de la connexion au backend'}><span/>{health.data ? 'Services connectés' : health.error ? 'Connexion indisponible' : 'Connexion…'}</div></header>
      <main id="main-content" tabIndex={-1}><Outlet/></main><footer className="app-footer"><span>DocuMind AI <span className="footer-dot">·</span> L’essentiel de vos documents.</span><span>Bêta en préparation <span className="footer-dot">·</span> IA indisponible pour la bêta</span><LegalNavigation/></footer>
    </div>
    {guide && <Modal title="Votre premier document" onClose={() => setGuide(false)}><ol className="guide-steps"><li><strong>Importez un PDF ou un TXT.</strong><p>Le texte est extrait et conservé page par page.</p></li><li><strong>Lancez l’analyse locale.</strong><p>Ajustez les réglages depuis la fiche du document.</p></li><li><strong>Explorez les résultats.</strong><p>Les fonctions IA sont indisponibles pour la bêta initiale. L’analyse classique est effectuée sur le serveur.</p></li></ol><button className="button primary" onClick={() => { setGuide(false); openUpload() }}><Plus size={17}/>Importer mon document</button></Modal>}
  </div>
}
