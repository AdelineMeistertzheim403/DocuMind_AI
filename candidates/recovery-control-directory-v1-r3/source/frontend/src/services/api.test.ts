import { describe, expect, it, vi } from 'vitest'
import { api, ApiError, validateFile } from './api'

describe('Service documentaire', () => {
  it('transmet le fichier au BFF sans clé et sans Content-Type fabriqué', async () => {
    const mock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'document' }), { status: 201 }))
    const file = new File(['contenu'], 'document.txt', { type: 'text/plain' })
    await expect(api.upload(file)).resolves.toEqual({ id: 'document' })
    const [url, options] = mock.mock.calls[0]
    expect(url).toBe('/bff/documents')
    expect(options?.headers).toBeUndefined()
    expect(options?.body).toBeInstanceOf(FormData)
    expect((options?.body as FormData).get('file')).toBe(file)
  })
  it('envoie les options réelles au lancement de l’analyse', async () => {
    const mock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'analysis' }), { status: 201 }))
    await api.analyze('id', { limite_phrase_longue: 40, mode_memoire: false })
    expect(mock.mock.calls[0][0]).toBe('/bff/documents/id/analyze')
    expect(JSON.parse(mock.mock.calls[0][1]?.body as string)).toEqual({ limite_phrase_longue: 40, mode_memoire: false })
  })
  it('gère la suppression 204 sans tenter de lire un JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.remove('id')).resolves.toBeUndefined()
  })
  it.each([401, 404, 413, 415, 422, 503])('conserve le code HTTP %i et le message contrôlé', async status => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Erreur du service' }), { status }))
    await expect(api.documents()).rejects.toMatchObject({ status, message: 'Erreur du service' })
  })
  it('gère une connexion interrompue', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('network'))
    await expect(api.documents()).rejects.toBeInstanceOf(ApiError)
  })
  it('valide extension, vide et taille avant import', () => {
    expect(validateFile(new File(['x'], 'image.png'), 10)).toContain('PDF ou TXT')
    expect(validateFile(new File([], 'empty.txt'), 10)).toContain('vide')
    expect(validateFile(new File(['long'], 'large.txt'), 2)).toContain('limite')
    expect(validateFile(new File(['ok'], 'test.PDF'), 10)).toBeNull()
  })
})
