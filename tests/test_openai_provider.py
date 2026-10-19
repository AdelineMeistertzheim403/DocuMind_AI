import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from backend.ai.providers import OpenAIProvider, ProviderError
from backend.ai.schemas import AnswerContent
from backend.config import Settings


def test_official_sdk_payload_store_false_and_reasoning_accounted():
    calls = []
    content = {'answer':'Contexte insuffisant.', 'insufficient_information':True, 'source_ids':[]}
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status='completed', output_text=json.dumps(content), usage=SimpleNamespace(input_tokens=100, output_tokens=80, output_tokens_details=SimpleNamespace(reasoning_tokens=20)))
    provider = OpenAIProvider(Settings(_env_file=None), SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = provider.generate({'operation':'question', 'question':'Test', 'passages':[]}, AnswerContent, 'request-id')
    assert result.output_tokens == 80 and result.reasoning_tokens == 20
    assert calls[0]['store'] is False and calls[0]['max_output_tokens'] == 1200
    assert calls[0]['text']['format']['strict']
    assert calls[0]['input'][0]['role'] == 'user' and 'NON FIABLES' in calls[0]['instructions']
    assert 'tools' not in calls[0]


@pytest.mark.parametrize('kind,expected_calls,uncertain', [('429',2,False), ('timeout',1,True), ('500',1,True)])
def test_retries_only_a_definitive_429(kind, expected_calls, uncertain):
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        request=httpx.Request('POST','https://api.openai.com/v1/responses')
        if kind=='timeout': raise openai.APITimeoutError(request=request)
        response=httpx.Response(int(kind), request=request)
        exception=openai.RateLimitError if kind=='429' else openai.InternalServerError
        raise exception('mock', response=response, body={})
    provider=OpenAIProvider(Settings(_env_file=None), SimpleNamespace(responses=SimpleNamespace(create=create)))
    with pytest.raises(ProviderError) as error:
        provider.generate({'operation':'question'}, AnswerContent, 'id')
    assert error.value.uncertain == uncertain and len(calls)==expected_calls


@pytest.mark.parametrize('status,reason,text,refusal,code', [
    ('incomplete','max_output_tokens','{',False,'output_truncated'),
    ('completed',None,'',True,'provider_refusal'),
    ('completed',None,'broken JSON',False,'invalid_json'),
])
def test_invalid_response_has_safe_reason_and_keeps_billed_usage(status,reason,text,refusal,code):
    response=SimpleNamespace(status=status,output_text=text,
        incomplete_details=SimpleNamespace(reason=reason),
        output=[SimpleNamespace(content=[SimpleNamespace(type='refusal')])] if refusal else [],
        usage=SimpleNamespace(input_tokens=100,output_tokens=80,output_tokens_details=None))
    provider=OpenAIProvider(Settings(_env_file=None),SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:response)))
    result=provider.generate({'operation':'question'},AnswerContent,'id')
    from backend.ai.service import validate_content
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:validate_content(result,AnswerContent,set())
    assert error.value.detail['code']==code
    assert result.input_tokens==100 and result.output_tokens==80


def test_generated_reference_schema_only_allows_actual_context_sources():
    from backend.ai.long_plan import intermediate_schema
    from backend.ai.providers import output_schema,input_bound
    schema=intermediate_schema(1080)
    data={'operation':'synthesis','partial_summaries':[
        {'summary':'A','source_ids':['first','second']},
        {'summary':'B','source_ids':['second','third']}]}
    definition=output_schema(data,schema)
    assert definition['properties']['source_ids']['items']['enum']==['first','second','third']
    assert definition['properties']['source_ids']['maxItems']==4
    assert 'enum' not in schema.model_json_schema()['properties']['source_ids']['items']
    assert input_bound(data,schema)>len(json.dumps(data))


def test_duplicate_valid_citations_are_normalized_but_unknown_sources_are_rejected():
    from backend.ai.providers import ProviderResult
    from backend.ai.service import validate_content
    from backend.ai.long_plan import intermediate_schema
    from fastapi import HTTPException
    result=ProviderResult({'summary':'Valid text','source_ids':['known','known']},100,80)
    content=validate_content(result,intermediate_schema(1080),{'known'})
    assert content.source_ids==['known']
    result.content['source_ids']=['invented']
    with pytest.raises(HTTPException) as error:validate_content(result,intermediate_schema(1080),{'known'})
    assert error.value.detail['code']=='invalid_references'
