from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analyseur_documents.core.analyseur import TERMES_TECHNIQUES


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageOut(ORMModel):
    id: UUID
    page_number: int
    text: str


class DocumentOut(ORMModel):
    id: UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class DocumentDetail(DocumentOut):
    pages: list[PageOut]


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
    offset: int
    limit: int


class AnalyzeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limite_phrase_longue: int = Field(35, ge=5, le=500)
    termes_techniques: list[str] = Field(default_factory=lambda: list(TERMES_TECHNIQUES), max_length=100)
    mode_memoire: bool = True
    filtrer_blocs_non_narratifs_actif: bool = True
    ignorer_titres: bool = True

    # Bounds apply to each term as well as the number of terms.
    @field_validator("termes_techniques")
    @classmethod
    def term_lengths(cls, terms):
        if any(not term.strip() or len(term) > 100 for term in terms):
            raise ValueError("Les termes doivent contenir entre 1 et 100 caractères")
        return terms


class TextLocation(BaseModel):
    page: int | None
    texte: str


class BulletList(BaseModel):
    page: int | None
    elements: list[TextLocation]


class Structure(BaseModel):
    nombre_lignes_textuelles: int
    nombre_listes_puces: int
    nombre_elements_listes_puces: int
    listes_puces: list[BulletList]


class LongSentence(BaseModel):
    phrase: str
    nombre_mots: int
    page: int | None
    nombre_virgules: int
    nombre_parentheses: int
    connecteurs: list[str]
    alertes: list[str]
    suggestion: str


class Readability(BaseModel):
    score: int
    niveau: str
    moyenne_mots_phrase: float
    pourcentage_phrases_longues: float


class StyleIndex(BaseModel):
    score: int
    niveau: str
    signaux: list[str]
    details: dict[str, int]
    diversite_lexicale: float
    regularite_phrases: float
    note: str


class TermCount(BaseModel):
    terme: str
    occurrences: int


class QualitySummary(BaseModel):
    niveau: str
    score: int
    points_forts: list[str]
    points_a_ameliorer: list[str]
    recommandations: list[str]


class AnalysisResult(BaseModel):
    nombre_caracteres: int
    nombre_mots: int
    nombre_phrases: int
    structure_document: Structure
    mots_frequents: list[tuple[str, int]]
    phrases_longues: list[LongSentence]
    longueurs_phrases: list[int]
    repartition_longueurs: dict[str, int]
    phrases_longues_par_page: dict[int, int]
    alertes_complexite: dict[str, int]
    connecteurs_frequents: dict[str, int]
    formules_generiques: dict[str, int]
    indice_style_artificiel: StyleIndex
    lisibilite: Readability
    termes_techniques: list[TermCount]
    termes_techniques_absents: list[str]
    resume_qualite: QualitySummary


class AnalysisOut(ORMModel):
    id: UUID
    document_id: UUID
    engine_version: str
    parameters: AnalyzeOptions
    result: AnalysisResult
    created_at: datetime


class ErrorOut(BaseModel):
    detail: str


class HealthOut(BaseModel):
    status: str
    database: str
