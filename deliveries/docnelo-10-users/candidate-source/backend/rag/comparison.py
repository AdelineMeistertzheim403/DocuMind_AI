import re
import unicodedata
from collections import defaultdict, deque
from difflib import SequenceMatcher

from ..ai.service import fail
from .schemas import Change, DiffSide


def blocks(document, settings):
    result, length = [], 0
    for page in document.pages:
        length += len(page.text)
        if length > settings.comparison_max_chars:
            fail('comparison_limit', 413)
        for paragraph in re.split(r'\n\s*\n', page.text):
            text = unicodedata.normalize('NFC', re.sub(r'\s+', ' ', paragraph).strip())
            if text:
                result.append((text, DiffSide(text=paragraph.strip(), pages=[page.page_number])))
            if len(result) > settings.comparison_max_blocks:
                fail('comparison_limit', 413)
    return result


def compare(a, b, settings):
    before, after = blocks(a, settings), blocks(b, settings)
    changes, removed, added, unchanged = [], [], [], 0
    matcher = SequenceMatcher(a=[item[0] for item in before], b=[item[0] for item in after], autojunk=False)
    for operation, a0, a1, b0, b1 in matcher.get_opcodes():
        if operation == 'equal':
            unchanged += a1-a0
        else:
            removed.extend(before[a0:a1]); added.extend(after[b0:b1])
    # Pair exact paragraphs first, including duplicate occurrences, to recognize moves.
    locations = defaultdict(deque)
    for index, (text, side) in enumerate(added):
        locations[text].append(index)
    used, remaining = set(), []
    for text, side in removed:
        if locations[text]:
            index = locations[text].popleft(); used.add(index)
            changes.append(('moved', side, added[index][1]))
        else:
            remaining.append((text, side))
    new = [item for index, item in enumerate(added) if index not in used]
    # Pair sufficiently related replacements; unrelated paragraphs remain remove/add.
    for text, side in remaining:
        best, similarity = None, .45
        words = set(text.split())
        candidates = sorted(range(len(new)), key=lambda index: -len(words.intersection(new[index][0].split())))[:3]
        for index in candidates:
            candidate = new[index][0]
            # Bounded prefix comparison avoids quadratic character diff on huge paragraphs.
            ratio = SequenceMatcher(a=text[:2000], b=candidate[:2000], autojunk=True).ratio()
            if ratio > similarity:
                best, similarity = index, ratio
        if best is None:
            changes.append(('removed', side, None))
        else:
            changes.append(('modified', side, new.pop(best)[1]))
    changes.extend(('added', None, side) for _, side in new)
    return [Change(id=f'change-{index+1}', kind=kind, before=left, after=right)
            for index, (kind, left, right) in enumerate(changes)], unchanged
