import math
import re
import unicodedata
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select

from ..models import DocumentChunk, DocumentPage
from .providers import input_bound
from .schemas import AnswerContent, SummaryContent

STOP = set('le la les de des du un une et en est au aux pour par avec dans sur que qui quoi quel quelle quels quelles comment pourquoi document'.split())


def terms(text):
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    return [word for word in re.findall(r'\w+', normalized) if len(word) > 1 and word not in STOP]


def load_passages(session, document_id):
    rows = session.execute(select(DocumentChunk, DocumentPage.page_number).join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
                           .where(DocumentChunk.document_id == document_id, DocumentPage.document_id == document_id)
                           .order_by(DocumentChunk.chunk_index)).all()
    return [{'chunk_id': str(chunk.id), 'page_number': number, 'text': chunk.text} for chunk, number in rows if chunk.text.strip()]


def relevant_passages(passages, question, settings):
    query = set(terms(question))
    counts = [Counter(terms(item['text'])) for item in passages]
    frequencies = {word: sum(word in words for words in counts) for word in query}
    ranked = []
    for index, words in enumerate(counts):
        score = sum((1 + math.log(1 + words[word])) * math.log(1 + len(passages) / (1 + frequencies[word]))
                    for word in query if words[word])
        if score > 0:
            ranked.append((score, index))
    selected = []
    for _, index in sorted(ranked, key=lambda item: (-item[0], item[1]))[:settings.ai_max_question_chunks]:
        candidate = [*selected, passages[index]]
        if input_bound({'operation': 'question', 'question': question, 'passages': candidate}, AnswerContent) <= settings.ai_max_input_tokens:
            selected = candidate
    return selected


def summary_groups(passages, settings):
    groups, current = [], []
    for passage in passages:
        if input_bound({'operation': 'summary', 'passages': [*current, passage]}, SummaryContent) > settings.ai_max_input_tokens:
            if not current:
                raise HTTPException(413, {'code': 'context_limit', 'message': 'Un passage dépasse la limite de contexte. Aucun envoi effectué.'})
            groups.append(current)
            current = [passage]
            if input_bound({'operation': 'summary', 'passages': current}, SummaryContent) > settings.ai_max_input_tokens:
                raise HTTPException(413, {'code': 'context_limit', 'message': 'Un passage dépasse la limite de contexte.'})
        else:
            current.append(passage)
    if current:
        groups.append(current)
    steps = len(groups) + (1 if len(groups) > 1 else 0)
    if steps > settings.ai_max_summary_steps:
        raise HTTPException(413, {'code': 'document_too_long', 'message': f'Document trop long : {steps} étapes nécessaires, limite {settings.ai_max_summary_steps}. Aucun texte envoyé. Réduisez le document ou ajustez les limites serveur.'})
    if not groups:
        raise HTTPException(422, {'code': 'no_text', 'message': 'Aucun passage textuel disponible.'})
    return groups
