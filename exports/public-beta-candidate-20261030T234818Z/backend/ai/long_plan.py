"""Conservative byte/token upper bounds and a deterministic, bounded reduction tree."""
import re

from pydantic import Field, create_model

from .providers import input_bound
from .schemas import StrictModel, SummaryContent
from .retrieval import load_passages
from .service import fail, cost


def intermediate_schema(max_chars):
    return create_model('IntermediateSummary', __base__=StrictModel,
        summary=(str, Field(min_length=1, max_length=max_chars)),
        source_ids=(list[str], Field(min_length=1, max_length=4)))


class LongDocumentSummarizer:
    def __init__(self, settings):
        self.settings = settings
        # This application stays well below the documented model context and long-context tariff threshold.
        self.input_limit = min(settings.ai_max_input_tokens,
                               settings.ai_model_context_tokens - settings.ai_max_output_tokens)
        if self.input_limit < 3500:
            fail('context_limit', 413)
        # Bound even JSON control-character escapes: 6 bytes/character, two children.
        self.summary_chars = self._compact_limit()
        self.schema = intermediate_schema(self.summary_chars)

    def _compact_limit(self):
        for limit in range(1800, 19, -20):
            schema = intermediate_schema(limit)
            children = [{'summary':'\x01'*limit,
                         'source_ids':[f'00000000-0000-0000-0000-{index:012d}' for index in range(start,start+4)]}
                        for start in (1,5)]
            payload = {'operation':'synthesis', 'partial_summaries':children}
            if max(input_bound(payload, schema),input_bound(payload, SummaryContent)) <= self.input_limit:
                return limit
        fail('context_limit',413)

    def fits(self, passages, final=False):
        return input_bound({'operation':'summary','passages':passages},SummaryContent if final else self.schema) <= self.input_limit

    def fragments(self, passages):
        # Preserve source chunk IDs; paragraph/sentence splits alter no stored text.
        split = []
        for passage in passages:
            start = 0
            for boundary in re.finditer(r'\n\s*\n', passage['text']):
                split.append({**passage,'text':passage['text'][start:boundary.end()]})
                start=boundary.end()
            if start<len(passage['text']): split.append({**passage,'text':passage['text'][start:]})
        for passage in split:
            text = passage['text']
            start = 0
            while start < len(text):
                low, high = 1, len(text)-start
                while low < high:
                    middle=(low+high+1)//2
                    if self.fits([{**passage,'text':text[start:start+middle]}]): low=middle
                    else: high=middle-1
                end=start+low
                if end<len(text):
                    prefix=text[start:end]
                    breaks=[match.end() for match in re.finditer(r'\n\s*\n|(?<=[.!?])\s+',prefix)]
                    if breaks and breaks[-1]>len(prefix)//2:
                        end=start+breaks[-1]
                fragment={**passage,'text':text[start:end]}
                if not self.fits([fragment]): fail('context_limit',413)
                yield fragment
                start=end

    def plan(self, session, document):
        passages=load_passages(session,document.id)
        if not passages: fail('no_text',422)
        total_pages=len(document.pages)
        empty_pages=[page.page_number for page in document.pages if not page.text.strip()]
        if self.fits(passages,final=True):
            groups=[passages]
        else:
            groups,current=[],[]
            for passage in self.fragments(passages):
                heading=bool(re.match(r'\s*(?:chapitre|partie|section|\d+(?:\.\d+)*[.)]?\s+)',passage['text'],re.I))
                full=not self.fits([*current,passage])
                section=heading and current and input_bound({'operation':'summary','passages':current},self.schema)>self.input_limit*.55
                if current and (full or section):
                    groups.append(current)
                    overlap=self.settings.long_summary_overlap_chars
                    tail={**current[-1],'text':current[-1]['text'][-overlap:]} if overlap else None
                    current=[tail] if tail and self.fits([tail,passage]) else []
                current.append(passage)
                if len(groups)>=self.settings.long_summary_max_parts: fail('document_too_long',413)
            if current: groups.append(current)
        nodes=[{'id':f'map-{index}','passages':group,'parents':[]} for index,group in enumerate(groups)]
        level=[node['id'] for node in nodes]
        depth=0
        while len(level)>1:
            depth+=1; next_level=[]
            for index in range(0,len(level),2):
                parents=level[index:index+2]
                if len(parents)==1:
                    next_level.append(parents[0]); continue
                identifier=f'reduce-{depth}-{index//2}'
                nodes.append({'id':identifier,'parents':parents})
                next_level.append(identifier)
            level=next_level
        if len(groups)>self.settings.long_summary_max_parts or len(nodes)>self.settings.long_summary_max_calls:
            fail('document_too_long',413)
        return {'direct':len(groups)==1, 'parts':len(groups), 'steps':len(nodes), 'levels':depth+1,
            'root':level[0], 'nodes':nodes,'summary_chars':self.summary_chars,
            'pages_total':total_pages,'empty_pages':empty_pages,
            'maximum_usd':str(cost(self.settings,self.settings.ai_max_input_tokens,self.settings.ai_max_output_tokens)*len(nodes)*2),
            'input_limit':self.input_limit,'overlap_chars':self.settings.long_summary_overlap_chars}
