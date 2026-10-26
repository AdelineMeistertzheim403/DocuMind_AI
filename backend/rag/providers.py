import hashlib
import math
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol

from ..ai.providers import ProviderError, ProviderResult, ensure_ai_enabled
from ..ai.settings_api import settings_for_request
from ..ai.retrieval import terms


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    input_tokens: int


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str], request_id: str) -> EmbeddingResult: ...


def runtime_settings(app, session, context):
    ensure_ai_enabled(app.state.settings)
    if context is not None and context.expires_at <= time.time():
        raise ProviderError('byok_disconnected', 403, False, 0)
    settings = settings_for_request(SimpleNamespace(app=app, state=SimpleNamespace(user_session=context)), session)
    if settings.ai_mode == 'USER_BYOK' and settings.ai_configuration_reason:
        raise ProviderError(settings.ai_configuration_reason, 403, False, 0)
    return settings


class OpenAIEmbeddingProvider:
    def __init__(self, settings, client=None):
        ensure_ai_enabled(settings)
        from openai import OpenAI
        import logging
        logging.getLogger('openai').setLevel(logging.WARNING)
        self.settings = settings
        self.enabled_check = None
        self.client = client or OpenAI(api_key=settings.openai_api_key.get_secret_value(), max_retries=0,
            timeout=settings.ai_timeout_seconds, base_url='https://api.openai.com/v1')

    def embed(self, texts, request_id):
        ensure_ai_enabled(self.settings)
        if self.enabled_check is not None:self.enabled_check()
        import openai
        try:
            response = self.client.embeddings.create(model=self.settings.embedding_model,
                dimensions=self.settings.embedding_dimensions, input=texts, encoding_format='float',
                extra_headers={'X-Client-Request-Id': request_id})
            if response.usage is None:
                raise ProviderError('usage_unknown', 503, True)
            rows = sorted(response.data, key=lambda item: item.index)
            vectors = [item.embedding for item in rows] if [item.index for item in rows] == list(range(len(texts))) else []
            return EmbeddingResult(vectors, response.usage.prompt_tokens)
        except openai.RateLimitError:
            raise ProviderError('provider_rate_limit', 429, False) from None
        except (openai.APIConnectionError, openai.APITimeoutError):
            raise ProviderError('provider_uncertain', 503, True) from None
        except openai.APIStatusError as exc:
            raise ProviderError('provider_unavailable', 503, exc.status_code >= 500) from None

    def close(self):
        self.client.close()


class MockEmbeddingProvider:
    def __init__(self, dimensions=1536):
        self.dimensions, self.calls = dimensions, []

    def embed(self, texts, request_id):
        self.calls.append((texts, request_id))
        result = []
        for text in texts:
            vector = [0.] * self.dimensions
            for word in terms(text) or ['empty']:
                index = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], 'big') % self.dimensions
                vector[index] += 1
            norm = math.sqrt(sum(value * value for value in vector))
            result.append([value / norm for value in vector])
        return EmbeddingResult(result, sum(max(1, len(text.encode()) // 4) for text in texts))


def validate_vectors(result, count, dimensions):
    if len(result.vectors) != count or any(len(vector) != dimensions or
        not all(math.isfinite(value) for value in vector) or sum(value * value for value in vector) <= 0
        for vector in result.vectors):
        raise ProviderError('invalid_output', 502, False, 0)


def embed(app, settings, texts, request_id):
    def check_enabled():
        ensure_ai_enabled(app.state.settings)
        ensure_ai_enabled(settings)
    check_enabled()
    if any(not text.strip() or len(text.encode()) > 8000 for text in texts):
        raise ProviderError('context_limit', 413, False, 0)
    provider = app.state.embedding_provider
    if provider is not None:
        return provider.embed(texts, request_id)
    provider = MockEmbeddingProvider(settings.embedding_dimensions) if settings.ai_provider == 'mock' else OpenAIEmbeddingProvider(settings)
    provider.enabled_check = check_enabled
    try:
        return provider.embed(texts, request_id)
    finally:
        close = getattr(provider, 'close', None)
        if close:
            close()


def usage(result):
    return ProviderResult({}, result.input_tokens, 0)
