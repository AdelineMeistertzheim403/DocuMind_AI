import pytest

from analyseur_documents.core.analyseur import analyser_texte
from backend.config import Settings
from backend.schemas import AnalysisResult, AnalyzeOptions
from backend.services.worker import analyze, run_worker
from fastapi import HTTPException


def test_engine_adapter_preserves_algorithms():
    text = "Docker utilise une API. Docker retourne des documents."
    options = AnalyzeOptions(mode_memoire=False, ignorer_titres=False).model_dump()
    marked = f"@@PAGE:1@@ @@PDFPAGE:1@@ {text}"
    expected = analyser_texte(marked, **options)
    actual = analyze([text], options)
    assert actual == expected
    validated = AnalysisResult.model_validate(actual)
    assert validated.nombre_mots == 8
    assert validated.mots_frequents[0] == ("docker", 2)


def test_uploaded_page_markers_cannot_spoof_locations():
    text = "@@PAGE:999@@ " + " ".join(["document"] * 40) + "."
    result = analyze([text], AnalyzeOptions(mode_memoire=False).model_dump())
    assert result["phrases_longues"][0]["page"] == 1


def test_worker_deadline_and_cleanup():
    settings = Settings(_env_file=None, worker_timeout_seconds=0.001)
    with pytest.raises(HTTPException) as error:
        run_worker(settings, "analyze", ["Texte."], AnalyzeOptions().model_dump())
    assert error.value.status_code == 422
