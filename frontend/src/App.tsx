import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { Layout } from './components/Layout'
import { WorkspaceProvider } from './components/Workspace'
import { EmptyState, Spinner } from './components/ui'
import { Dashboard } from './pages/Dashboard'
import { Documents } from './pages/Documents'
import { DocumentDetailPage } from './pages/DocumentDetail'
import { ApiError } from './services/api'
import { AISettingsPage } from './pages/AISettings'
import { IntelligentLibrary } from './pages/IntelligentLibrary'
import { CompareDocuments } from './pages/CompareDocuments'
import {RequireAccount,AccountAccess,ProfilePage,SecurityPage,PrivacyPage} from './pages/Account'

const AnalysisPage = lazy(() => import('./pages/Analysis').then(module => ({ default: module.AnalysisPage })))

export function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { staleTime: 15000,
    retry: (count, error) => !(error instanceof ApiError && [401, 404, 422].includes(error.status)) && count < 1,
    refetchOnWindowFocus: false,
  }, mutations: { retry: false } } })
}
export function AppRoutes() {
  return <WorkspaceProvider><Routes>
    <Route path="login" element={<AccountAccess mode="login"/>}/>
    <Route path="register" element={<AccountAccess mode="register"/>}/>
    <Route path="forgot-password" element={<AccountAccess mode="forgot"/>}/>
    <Route path="reset-password" element={<AccountAccess mode="reset"/>}/>
    <Route element={<RequireAccount/>}><Route element={<Layout/>}>
    <Route index element={<Dashboard/>}/><Route path="documents" element={<Documents/>}/>
    <Route path="documents/:id" element={<DocumentDetailPage/>}/><Route path="documents/:id/analysis" element={<Suspense fallback={<Spinner label="Ouverture des résultats…"/>}><AnalysisPage/></Suspense>}/>
    <Route path="settings/ai" element={<AISettingsPage/>}/>
    <Route path="settings/profile" element={<ProfilePage/>}/>
    <Route path="settings/security" element={<SecurityPage/>}/>
    <Route path="settings/privacy" element={<PrivacyPage/>}/>
    <Route path="library" element={<IntelligentLibrary/>}/>
    <Route path="compare" element={<CompareDocuments/>}/>
    <Route path="comparisons/:id" element={<CompareDocuments/>}/>
    <Route path="*" element={<div className="page"><EmptyState title="Cette page est introuvable" action={<Link className="button primary" to="/">Revenir au tableau de bord</Link>}>Retrouvez vos documents depuis la navigation.</EmptyState></div>}/>
  </Route></Route></Routes></WorkspaceProvider>
}
const client = makeQueryClient()
export default function App() { return <QueryClientProvider client={client}><BrowserRouter><AppRoutes/></BrowserRouter></QueryClientProvider> }
