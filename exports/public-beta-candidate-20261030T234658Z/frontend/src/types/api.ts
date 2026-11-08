export interface DocumentSummary {
  id: string; filename: string; media_type: string; size_bytes: number; sha256: string; created_at: string
}
export interface DocumentPage { id: string; page_number: number; text: string }
export interface DocumentDetail extends DocumentSummary { pages: DocumentPage[] }
export interface DocumentList { items: DocumentSummary[]; total: number; offset: number; limit: number }
export interface AnalyzeOptions {
  limite_phrase_longue: number; termes_techniques?: string[]; mode_memoire: boolean;
  filtrer_blocs_non_narratifs_actif: boolean; ignorer_titres: boolean
}
export interface TextLocation { page: number | null; texte: string }
export interface LongSentence {
  phrase: string; nombre_mots: number; page: number | null; nombre_virgules: number;
  nombre_parentheses: number; connecteurs: string[]; alertes: string[]; suggestion: string
}
export interface AnalysisResult {
  nombre_caracteres: number; nombre_mots: number; nombre_phrases: number;
  structure_document: {
    nombre_lignes_textuelles: number; nombre_listes_puces: number; nombre_elements_listes_puces: number;
    listes_puces: { page: number | null; elements: TextLocation[] }[]
  };
  mots_frequents: [string, number][]; phrases_longues: LongSentence[]; longueurs_phrases: number[];
  repartition_longueurs: Record<string, number>; phrases_longues_par_page: Record<string, number>;
  alertes_complexite: Record<string, number>; connecteurs_frequents: Record<string, number>;
  formules_generiques: Record<string, number>;
  indice_style_artificiel: {
    score: number; niveau: string; signaux: string[]; details: Record<string, number>;
    diversite_lexicale: number; regularite_phrases: number; note: string
  };
  lisibilite: { score: number; niveau: string; moyenne_mots_phrase: number; pourcentage_phrases_longues: number };
  termes_techniques: { terme: string; occurrences: number }[]; termes_techniques_absents: string[];
  resume_qualite: { niveau: string; score: number; points_forts: string[]; points_a_ameliorer: string[]; recommandations: string[] }
}
export interface Analysis {
  id: string; document_id: string; engine_version: string; parameters: AnalyzeOptions;
  result: AnalysisResult; created_at: string
}
export interface Health { status: string; database: string }
