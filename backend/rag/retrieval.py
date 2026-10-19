import math
from collections import Counter

from sqlalchemy import select

from ..models import Document, DocumentChunk, DocumentPage
from ..ai.retrieval import terms
from ..ai.service import fail
from .indexing import config_filter
from .models import ChunkEmbedding
from .schemas import Passage, SearchOut


class HybridRetriever:
    def __init__(self, session, settings, owner, identifiers):
        self.session, self.settings, self.owner, self.ids = session, settings, owner, identifiers

    def base(self):
        return select(DocumentChunk, DocumentPage.page_number, Document.filename).join(Document, Document.id == DocumentChunk.document_id).join(
            DocumentPage, DocumentPage.id == DocumentChunk.page_id).where(Document.owner_id == self.owner,
            Document.id.in_(self.ids), DocumentPage.document_id == Document.id)

    def indexed(self):
        return self.session.scalar(select(ChunkEmbedding.id).join(Document, Document.id == ChunkEmbedding.document_id).where(
            Document.owner_id == self.owner, ChunkEmbedding.owner_id == self.owner,
            Document.id.in_(self.ids), *config_filter(ChunkEmbedding, self.settings)).limit(1)) is not None

    def search(self, query, limit, vector=None):
        rows = self.session.execute(self.base().order_by(Document.id, DocumentChunk.chunk_index).limit(self.settings.rag_max_chunks + 1)).all()
        if len(rows) > self.settings.rag_max_chunks:
            fail('document_limit', 413)
        by_id = {chunk.id: (chunk, page, filename) for chunk, page, filename in rows}
        words = set(terms(query))
        counts = {identifier: Counter(terms(row[0].text)) for identifier, row in by_id.items()}
        frequencies = {word: sum(word in counter for counter in counts.values()) for word in words}
        scores = {identifier: sum((1 + math.log1p(counter[word])) * math.log1p(len(rows) / (1 + frequencies[word]))
                    for word in words if counter[word]) for identifier, counter in counts.items()}
        lexical = [identifier for identifier in sorted(scores, key=lambda value: (-scores[value], str(value))) if scores[identifier] > 0][:100]
        distances = {}
        if vector is not None:
            if self.session.bind.dialect.name == 'postgresql':
                distance = ChunkEmbedding.vector.cosine_distance(vector)
                found = self.session.execute(select(ChunkEmbedding.chunk_id, distance).join(Document, Document.id == ChunkEmbedding.document_id)
                    .join(DocumentChunk, DocumentChunk.id == ChunkEmbedding.chunk_id).where(Document.owner_id == self.owner,
                        ChunkEmbedding.owner_id == self.owner, Document.id.in_(self.ids), DocumentChunk.document_id == Document.id,
                        *config_filter(ChunkEmbedding, self.settings)).order_by(distance, ChunkEmbedding.chunk_id).limit(100)).all()
                distances = dict(found)
            else:
                # SQLite is only a portable test fallback; production uses the native cosine operator.
                embeddings = self.session.scalars(select(ChunkEmbedding).join(Document, Document.id == ChunkEmbedding.document_id).where(
                    Document.owner_id == self.owner, ChunkEmbedding.owner_id == self.owner, Document.id.in_(self.ids),
                    *config_filter(ChunkEmbedding, self.settings))).all()
                norm = math.sqrt(sum(x*x for x in vector))
                distances = {row.chunk_id: 1 - sum(a*b for a,b in zip(row.vector, vector)) /
                    (norm * math.sqrt(sum(x*x for x in row.vector))) for row in embeddings if row.chunk_id in by_id}
        vector_ids = sorted(distances, key=lambda value: (distances[value], str(value)))[:100]
        ranks_a, ranks_b = ({value: rank for rank, value in enumerate(items, 1)} for items in (lexical, vector_ids))
        fused = {identifier: (1/(60+ranks_a[identifier]) if identifier in ranks_a else 0) +
            (1/(60+ranks_b[identifier]) if identifier in ranks_b else 0) for identifier in set(lexical) | set(vector_ids)}
        passages = []
        for identifier in sorted(fused, key=lambda value: (-fused[value], str(value)))[:min(limit, self.settings.rag_max_passages)]:
            chunk, page, filename = by_id[identifier]
            passages.append(Passage(chunk_id=identifier, document_id=chunk.document_id, filename=filename, page_number=page,
                start_char=chunk.start_char, end_char=chunk.end_char, excerpt=chunk.text, rrf_score=fused[identifier],
                lexical_rank=ranks_a.get(identifier), vector_rank=ranks_b.get(identifier), cosine_distance=distances.get(identifier)))
        return SearchOut(passages=passages, strategy='hybrid_rrf' if vector is not None else 'lexical',
            notice='Le rang et la distance mesurent la pertinence, pas la véracité. Indexation partielle possible ; les passages non indexés restent recherchables lexicalement.')
