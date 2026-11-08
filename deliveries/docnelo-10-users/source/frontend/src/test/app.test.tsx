import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes, makeQueryClient } from '../App'
import { api, ApiError } from '../services/api'
import { document, analysis } from './fixtures'
import { ai } from '../services/ai'
import {account} from '../services/account'
import {longSummary} from '../services/longSummary'

function mount(path = '/') {
  const client = makeQueryClient()
  client.setQueryData(['account'],{id:'test-user',email:'test@example.test',username:'test',owner_id:'test-owner',workspace:'Espace personnel'})
  client.setDefaultOptions({ queries: { retry: false, gcTime: 0 }, mutations: { retry: false } })
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppRoutes/></MemoryRouter></QueryClientProvider>)
  return { ...view, client, user: userEvent.setup() }
}
beforeEach(() => {
  vi.spyOn(account,'me').mockResolvedValue({id:'test-user',email:'test@example.test',username:'test',owner_id:'test-owner',workspace:'Espace personnel'})
  vi.spyOn(longSummary,'plan').mockResolvedValue({direct:true,parts:1,steps:1,levels:1,root:'map-0',summary_chars:100,pages_total:1,empty_pages:[],maximum_usd:.01,input_limit:16000,overlap_chars:200})
  vi.spyOn(ai, 'status').mockResolvedValue({ mode:'OWNER_DEMO', enabled:false, available:false, reason:'disabled', provider:'openai', model:'gpt-5.6-luna', budget_usd:4, spent_usd:0, reserved_usd:0, remaining_usd:4, summary_quota:20, question_quota:100, summaries_used:0, questions_used:0, requests:0, provider_calls:0, input_tokens:0, output_tokens:0, reasoning_tokens:0, pending_requests:0, pricing_verified_on:'2026-10-19' })
  vi.spyOn(ai, 'summaries').mockResolvedValue({ items: [], total: 0, offset: 0, limit: 10 })
  vi.spyOn(ai, 'history').mockResolvedValue({ items: [], total: 0, offset: 0, limit: 10 })
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', database: 'ok' })
  vi.spyOn(api, 'config').mockResolvedValue({ max_upload_bytes: 10485760 })
  vi.spyOn(api, 'documents').mockResolvedValue({ items: [document], total: 1, offset: 0, limit: 12 })
  vi.spyOn(api, 'document').mockResolvedValue(document)
  vi.spyOn(api, 'analysis').mockResolvedValue(analysis)
})

describe('Parcours documentaire', () => {
  it('navigue du tableau de bord vers la bibliothèque et le détail', async () => {
    const { user } = mount()
    await screen.findByRole('heading', { name: 'Tableau de bord' })
    await user.click(screen.getByRole('link', { name: /^Documents$/ }))
    await screen.findByRole('heading', { name: /^Documents$/ })
    await user.click(await screen.findByRole('link', { name: /Exemple.txt Texte extrait/ }))
    expect(await screen.findByRole('heading', { name: 'Exemple.txt' })).toBeInTheDocument()
    expect(screen.getByText(document.pages[0].text)).toBeInTheDocument()
  })
  it('importe un TXT et ouvre sa fiche', async () => {
    const upload = vi.spyOn(api, 'upload').mockResolvedValue(document)
    const { user } = mount('/documents')
    await user.click(screen.getAllByRole('button', { name: 'Importer un document' })[0])
    const dialog = await screen.findByRole('dialog')
    const file = new File(['Docker utilise une API.'], 'test.txt', { type: 'text/plain' })
    await user.upload(within(dialog).getByLabelText('Fichier à importer'), file)
    await user.click(within(dialog).getByRole('button', { name: 'Importer le document' }))
    await waitFor(() => expect(upload).toHaveBeenCalledWith(file, expect.anything()))
    expect(await screen.findByRole('heading', { name: 'Exemple.txt' })).toBeInTheDocument()
  })
  it('affiche une erreur de fichier avant l’appel API', async () => {
    const upload = vi.spyOn(api, 'upload')
    const { user } = mount('/documents')
    await user.click(screen.getAllByRole('button', { name: 'Importer un document' })[0])
    const input = await screen.findByLabelText('Fichier à importer')
    await user.upload(input, new File([], 'vide.txt', { type: 'text/plain' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('vide')
    expect(upload).not.toHaveBeenCalled()
  })
  it('lance l’analyse puis affiche ses vrais résultats', async () => {
    const analyze = vi.spyOn(api, 'analyze').mockResolvedValue(analysis)
    const { user } = mount(`/documents/${document.id}`)
    await user.click(await screen.findByRole('button', { name: 'Lancer l’analyse' }))
    expect(await screen.findByRole('heading', { name: /Résultats d’analyse/ })).toBeInTheDocument()
    expect(analyze).toHaveBeenCalledWith(document.id, expect.objectContaining({ mode_memoire: false, limite_phrase_longue: 35 }))
    await user.click(screen.getByRole('button', { name: 'Résumé qualité' }))
    expect(await screen.findByText(/Il ne résume pas le sujet du document/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Indice de style' }))
    expect(await screen.findByText(analysis.result.indice_style_artificiel.note)).toBeInTheDocument()
  })
  it('demande confirmation avant de supprimer', async () => {
    const remove = vi.spyOn(api, 'remove').mockResolvedValue(undefined)
    const { user } = mount('/documents')
    await user.click(await screen.findByRole('button', { name: 'Supprimer Exemple.txt' }))
    expect(remove).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Conserver' }))
    expect(remove).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Supprimer Exemple.txt' }))
    await user.click(screen.getByRole('button', { name: 'Supprimer définitivement' }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith(document.id, expect.anything()))
    expect(await screen.findByText('Document supprimé.')).toBeInTheDocument()
  })
  it('affiche l’erreur 503 et permet de réessayer', async () => {
    vi.mocked(api.documents).mockRejectedValue(new ApiError(503, 'Service occupé'))
    mount('/documents')
    expect(await screen.findByRole('alert')).toHaveTextContent('Service occupé')
    expect(screen.getByRole('button', { name: /Réessayer/ })).toBeInTheDocument()
  })
  it('annonce explicitement une recherche limitée à la page chargée', async () => {
    const { user } = mount('/documents')
    await screen.findByRole('link', { name: /Exemple.txt Texte extrait/ })
    await user.type(screen.getByRole('textbox', { name: 'Rechercher dans la page chargée' }), 'introuvable')
    expect(await screen.findByText('Aucun résultat dans cette page')).toBeInTheDocument()
    expect(screen.getByText(/Recherche et filtres limités/)).toBeInTheDocument()
  })
  it('pagine via les paramètres réels offset et limit', async () => {
    vi.mocked(api.documents).mockImplementation(async (offset = 0, limit = 12) => ({ items: [document], total: 25, offset, limit }))
    const { user } = mount('/documents')
    await user.click(await screen.findByRole('button', { name: 'Page suivante' }))
    await waitFor(() => expect(api.documents).toHaveBeenLastCalledWith(12, 12, expect.any(AbortSignal)))
  })
  it('propose de lancer une analyse quand elle n’existe pas encore', async () => {
    vi.mocked(api.analysis).mockRejectedValue(new ApiError(404, 'Aucune analyse disponible'))
    mount(`/documents/${document.id}/analysis`)
    expect(await screen.findByRole('link', { name: 'Préparer l’analyse' })).toHaveAttribute('href', `/documents/${document.id}`)
  })
  it('affiche un état de chargement sans inventer de données', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof api.documents>>) => void
    vi.mocked(api.documents).mockReturnValue(new Promise(done => { resolve = done }))
    mount('/documents')
    expect(screen.getByRole('status')).toHaveTextContent('Chargement de votre bibliothèque')
    await act(async () => resolve({ items: [], total: 0, offset: 0, limit: 12 }))
    expect(await screen.findByText('Votre premier document vous attend')).toBeInTheDocument()
  })
})
