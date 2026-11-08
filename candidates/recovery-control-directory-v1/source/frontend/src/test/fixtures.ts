import type { Analysis, DocumentDetail } from '../types/api'

export const document: DocumentDetail = {
  id: '11111111-1111-4111-8111-111111111111', filename: 'Exemple.txt', media_type: 'text/plain',
  size_bytes: 50, sha256: 'a'.repeat(64), created_at: '2026-10-19T08:00:00Z',
  pages: [{ id: 'page-1', page_number: 1, text: 'Docker utilise une API. Cette API traite des documents.' }],
}
// Fixture de test seulement ; aucune donnée fictive n'est utilisée par les pages opérationnelles.
export const analysis: Analysis = {
  id: '22222222-2222-4222-8222-222222222222', document_id: document.id,
  engine_version: 'legacy-1', created_at: '2026-10-19T09:00:00Z',
  parameters: { limite_phrase_longue: 35, mode_memoire: false, ignorer_titres: true, filtrer_blocs_non_narratifs_actif: true, termes_techniques: ['Docker', 'API'] },
  result: {
    nombre_mots: 9, nombre_caracteres: 54, nombre_phrases: 2,
    structure_document: { nombre_lignes_textuelles: 1, nombre_listes_puces: 0, nombre_elements_listes_puces: 0, listes_puces: [] },
    mots_frequents: [['api', 2], ['docker', 1]], phrases_longues: [], longueurs_phrases: [4, 5],
    repartition_longueurs: { 'Courtes (0-15)': 2, 'Moyennes (16-30)': 0 },
    phrases_longues_par_page: {}, alertes_complexite: {}, connecteurs_frequents: {}, formules_generiques: {},
    indice_style_artificiel: { score: 0, niveau: 'Faible', signaux: ['Aucun signal stylistique fort détecté.'], details: {}, diversite_lexicale: 0.8, regularite_phrases: 0.8, note: 'Cet indice ne prouve pas qu’un texte a été généré par IA.' },
    lisibilite: { score: 100, niveau: 'Bonne', moyenne_mots_phrase: 4.5, pourcentage_phrases_longues: 0 },
    termes_techniques: [{ terme: 'API', occurrences: 2 }, { terme: 'Docker', occurrences: 1 }], termes_techniques_absents: [],
    resume_qualite: { niveau: 'Bonne', score: 100, points_forts: ['La lisibilité globale est bonne.'], points_a_ameliorer: [], recommandations: ['Aucune action prioritaire évidente.'] },
  },
}
