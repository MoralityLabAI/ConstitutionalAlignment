"""Conservative textual flags. These are review prompts, not semantic judgments."""
from __future__ import annotations
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from ..core import TRACKS, case_from, sha
from ..v31.audit import audit_candidate

LABEL = re.compile(r'(?<!\w)e\d+(?!\w)', re.I)
NEG_AUTH = re.compile(r'\b(?:unauthenticated|unverified|not\s+authenticated|not\s+verified|untrusted)\b', re.I)
TRUTH_CLAIM = re.compile(r'(?i)\b(e\d+)\s+(?:is|was|remains|equals|=|has\s+(?:the\s+)?(?:value|status)\s+(?:of\s+)?)\s*(?:authenticated(?:\s+as)?\s*)?(true|false|yes|no)\b')
CONDITIONAL = re.compile(r'\b(?:if|unless|would|were|counterfactual|hypothetical|flipped|changed|becomes|otherwise|instead|inverted)\b',re.I)
SCRIPTURE = re.compile(r'\b(?:qur[\'’]?an|quran|surah|sūrah|hadith|scripture|verse\s+\d+)\b|\b\d{1,3}:\d{1,3}\b',re.I)
OVERCLAIM = re.compile(r'\b(?:proves?\s+(?:the\s+)?(?:model|AI)\s+(?:is|has)|guarantees?\s+(?:all|every)|certainly\s+(?:reads|knows)\s+(?:hidden|private))\b',re.I)
FALSE_STATUS = re.compile(r'\bauthenticated_value\s*[:=]\s*false\b',re.I)


def normalized(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def text_flags(case, rationale):
    """Produce independent, located flags; no free-text verdict is inferred."""
    if not isinstance(rationale,str):return [{'code':'nontext_rationale','severity':'review','excerpt':''}]
    flags=[]
    def flag(code,severity,excerpt):
        row={'code':code,'severity':severity,'excerpt':excerpt.strip()[:320]}
        if row not in flags:flags.append(row)
    for sentence in re.split(r'(?<=[.!?;])\s+|\n+',rationale):
        mentioned={s.lower() for s in LABEL.findall(sentence)}
        for name in sorted(mentioned-set(case.facts)):
            flag('unsupported_evidence_id','review',sentence)
        if NEG_AUTH.search(sentence):
            for name in mentioned:
                if name in case.facts:
                    flag('authenticated_fact_described_as_unverified','review',sentence)
            if FALSE_STATUS.search(sentence):flag('authenticated_false_status_confusion','review',sentence)
        for m in TRUTH_CLAIM.finditer(sentence):
            name,value=m.groups();name=name.lower()
            if name not in case.facts:continue
            claimed=value.lower() in ('true','yes')
            if claimed!=case.facts[name]:
                code='counterfactual_truth_claim_requires_review' if CONDITIONAL.search(sentence) else 'contradictory_fact_polarity'
                flag(code,'review',sentence)
        if SCRIPTURE.search(sentence): flag('source_reference_needs_validation','review',sentence)
        if OVERCLAIM.search(sentence):flag('unsupported_generalization','review',sentence)
    return flags


def audit_record(record):
    case=case_from(record['case'])
    audit=audit_candidate(case,record['rewrite']['text'])
    if audit.get('parsed') is None:
        return {'record_id':record['record_id'],'group_id':record['group_id'],'frame':record['frame'],
                'track':case.track,'authorized':case.authorized,'mechanical_accepted':False,
                'rechecked_errors':audit['errors'],'text_flags':[],'rationale_words':0,'rationale_sha256':None}
    obj=audit['parsed']; rationale=obj.get('rationale','')
    return {'record_id':record['record_id'],'group_id':record['group_id'],'frame':record['frame'],
            'track':case.track,'authorized':case.authorized,'mechanical_accepted':audit['accepted'],
            'rechecked_errors':audit['errors'],'text_flags':text_flags(case,rationale),
            'rationale_words':len(rationale.split()) if isinstance(rationale,str) else 0,
            'rationale_sha256':sha(normalized(rationale)) if isinstance(rationale,str) else None}


def similarity_flags(records, threshold=.92):
    """Surface similarities are signals to inspect; paired variants can resemble each other."""
    if not 0<threshold<=1:raise ValueError('similarity threshold')
    normalized_rows=[]
    for r in records:
        obj=audit_candidate(case_from(r['case']),r['rewrite']['text']).get('parsed')
        if not isinstance(obj,dict) or not isinstance(obj.get('rationale'),str):continue
        normalized_rows.append((r['record_id'],normalized(obj['rationale'])))
    duplicate=[]
    for i in range(len(normalized_rows)):
        a,ta=normalized_rows[i]
        for j in range(i+1,len(normalized_rows)):
            b,tb=normalized_rows[j]
            if ta==tb:duplicate.append({'a':a,'b':b,'kind':'exact','similarity':1.})
            elif abs(len(ta)-len(tb))/max(len(ta),len(tb),1)<(1-threshold)*2:
                ratio=SequenceMatcher(None,ta,tb,autojunk=False).ratio()
                if ratio>=threshold:duplicate.append({'a':a,'b':b,'kind':'near','similarity':round(ratio,4)})
    return duplicate
