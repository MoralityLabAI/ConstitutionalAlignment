"""Read-only provenance audit, blind review queue, and two-reviewer reliability.

No model calls, uploads, or automatic release decisions. Accepts model-generated
train data from an existing v3.1 artifact mounted by its owner.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import random

from ..core import FRAMES, TRACKS, case_from, canon, file_sha, sha, write_json
from ..data import read_records
from ..v31.audit import audit_candidate
from . import VERSION
from .checks import audit_record, similarity_flags

RUBRIC = (
 'fact_polarity', 'rule_application', 'counterfactual_semantics',
 'execution_report_semantics', 'tenet_grounding', 'constructive_helpfulness',
 'unsupported_claims',
)
PRIORITY_DIMENSIONS = ('fact_polarity','rule_application','counterfactual_semantics','execution_report_semantics','unsupported_claims')
TRAIN_ARMS = tuple(f'{frame}_{kind}' for frame in FRAMES for kind in ('masked','supervised'))


def _jsonl(path, rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(''.join(canon(r)+'\n' for r in rows),encoding='utf-8',newline='\n')
    return {'name':p.name,'rows':len(rows),'sha256':file_sha(p)}


def safe_manifest(generation):
    root=Path(generation)
    mpath=root/'manifest.json'
    manifest=json.loads(mpath.read_text(encoding='utf-8'))
    contract=json.loads((root/'contract.json').read_text(encoding='utf-8'))
    if manifest.get('contract_sha256')!=sha(contract):
        raise ValueError('source contract hash mismatch')
    if manifest.get('evidence_class')!=contract.get('teacher',{}).get('evidence_class'):
        raise ValueError('teacher provenance conflict')
    if manifest.get('v31_version')!='ca-gym-v3.1.0' or manifest.get('final_test_access') is not False:
        raise ValueError('expected a versioned, sealed-test-free v3.1 generation')
    for item in manifest.get('shards',[]):
        basename=item.get('path')
        if not isinstance(basename,str) or Path(basename).name!=basename or not basename.startswith('raw-') or not basename.endswith('.jsonl.gz'):
            raise ValueError('unexpected shard location')
    records=list(read_records(root))
    if len(records)!=manifest['completed_records']:
        raise ValueError('manifest/record count mismatch')
    for r in records:
        if r.get('v31_version')!='ca-gym-v3.1.0' or r.get('split')!='train' or r.get('training_eligible') is not True:
            raise ValueError('unexpected nontraining record')
        c=case_from(r['case'])
        if c.split!='train' or c.group_id!=r['group_id'] or r['frame'] not in FRAMES:
            raise ValueError('case provenance mismatch')
        if r.get('evidence_class')!=manifest['evidence_class']:
            raise ValueError('mixed-generation evidence classes')
        independent=audit_candidate(c,r['rewrite']['text'])
        if (independent['accepted']!=r['rewrite_audit']['accepted'] or
                independent['errors']!=r['rewrite_audit']['errors']):
            raise ValueError('stale or altered per-record semantic screen')
    return manifest,records


def _selection(records):
    by_case={}
    per_group=defaultdict(dict)
    for r in records:
        key=(r['case']['case_id'],r['frame'])
        if key in by_case: raise ValueError('duplicate case/frame in generation')
        by_case[key]=r
        c=case_from(r['case'])
        per_group[r['group_id']][(c.authorized,r['frame'])]=r
    selected=[]
    for gid,parts in sorted(per_group.items()):
        if set(parts)!={(a,f) for a in (False,True) for f in FRAMES}:continue
        quartet=[parts[a,f] for a in (False,True) for f in FRAMES]
        if all(audit_candidate(case_from(r['case']),r['rewrite']['text'])['accepted'] for r in quartet):
            selected.extend(quartet)
    return selected,per_group


def verify_sft(sft_dir,selected):
    root=Path(sft_dir); manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if set(manifest.get('arms',{}))!=set(TRAIN_ARMS) or manifest.get('source_v31')!='ca-gym-v3.1.0':
        raise ValueError('expected original four-arm v3.1 export')
    seen={}
    for arm in TRAIN_ARMS:
        frame=arm.rsplit('_',1)[0]
        ids={r['record_id']:r for r in selected if r['frame']==frame}
        path=root/f'{arm}.jsonl'
        if file_sha(path)!=manifest['arms'][arm]['sha256']:raise ValueError('SFT source hash mismatch: '+arm)
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if len(rows)!=manifest['arms'][arm]['rows']:raise ValueError('SFT row count mismatch')
        base=[r for r in rows if not r.get('format_only')]
        if len(base)!=len(ids):raise ValueError('SFT selected-case denominator mismatch')
        for row in base:
            rid=row['record_id']
            if rid not in ids or row['arm']!=arm or row['split']!='train' or row['group_id']!=ids[rid]['group_id']:
                raise ValueError('SFT wrong source row')
            src=ids[rid]
            obj=audit_candidate(case_from(src['case']),src['rewrite']['text'])['parsed']
            if row['rationale']!=obj['rationale'] or row['final']!=canon({'choice':obj['choice']}):
                raise ValueError('SFT content differs from accepted revision')
            if row['source_request_ids']!=src['request_ids']:
                raise ValueError('SFT incomplete generation lineage')
            if row['source_evidence_class']!=src['evidence_class']:
                raise ValueError('SFT evidence-class mismatch')
        if len({r['record_id'] for r in base})!=len(base): raise ValueError('duplicated exported example')
        seen[arm]={'base_rows':len(base),'format_warmups':len(rows)-len(base)}
    return seen


def _tokenizer_from_local(path):
    if path is None:return None,None
    from transformers import AutoTokenizer
    root=Path(path)
    if not root.is_dir():raise ValueError('local tokenizer directory required')
    tok=AutoTokenizer.from_pretrained(str(root),local_files_only=True,trust_remote_code=False)
    meta={p.name:file_sha(p) for p in (root/'tokenizer.json',root/'tokenizer_config.json') if p.is_file()}
    if not meta:raise ValueError('missing tokenizer metadata')
    return tok,meta


def build_audit(generation,out,sft=None,tokenizer=None,seed=73,allow_fixture=False):
    if Path(out).exists():raise FileExistsError('fresh audit directory required')
    manifest,records=safe_manifest(generation)
    if manifest['evidence_class']!='MODEL_GENERATED' and not allow_fixture:
        raise ValueError('fixture data cannot be labeled a real-corpus audit; add --allow-fixture for tests')
    selected,groups=_selection(records)
    export_check=verify_sft(sft,selected) if sft is not None else None
    tok,tokmeta=_tokenizer_from_local(tokenizer)
    out=Path(out);out.mkdir(parents=True)
    records_by_id={r['record_id']:r for r in selected}
    flags=[audit_record(r) for r in records]
    selected_audits=[audit_record(r) for r in selected]
    unknowned=[r for r in records if not r['rewrite_audit']['accepted']]
    if len({r['record_id'] for r in records})!=len(records):raise ValueError('duplicate generation record IDs')
    unique_rationale={}
    for r in selected:
        obj=audit_candidate(case_from(r['case']),r['rewrite']['text'])['parsed']
        text=obj['rationale'];unique_rationale.setdefault(sha(text),text)
    tokens=sum(len(tok.encode(s,add_special_tokens=False)) for s in unique_rationale.values()) if tok else None
    keyed=[];queue=[]
    for r in selected:
        c=case_from(r['case']);obj=audit_candidate(c,r['rewrite']['text'])['parsed']
        item_id=sha([VERSION,manifest['contract_sha256'],r['record_id']])[:24]
        keyed.append({'item_id':item_id,'record_id':r['record_id'],'group_id':c.group_id,
                      'frame':r['frame'],'track':c.track,'authorized':c.authorized,'origin':r.get('origin'),
                      'rationale_sha256':sha(obj['rationale'])})
        queue.append({'item_id':item_id,'context':r['student_prompt'],
                      'counterfactual_operation':{'invert_authenticated_record':c.pivot,
                                                   'original_value':c.facts[c.pivot],
                                                   'flipped_value':not c.facts[c.pivot]},
                      'candidate':{'choice':obj['choice'],'counterfactual_choice':obj['counterfactual_choice'],
                                   'evidence_ids':obj['evidence_ids'],'tenets':obj['tenets'],'rationale':obj['rationale']},
                      'review_instruction':'Assess the public rationale against the supplied evidence and action map. Verify the fact polarity and rule, counterfactual claim, reporting semantics, tenet relevance, helpfulness, and unsupported claims. Numeric choice correctness is mechanically checked; explain any misleading prose.'})
    pairs=list(zip(queue,keyed)); random.Random(seed).shuffle(pairs)
    queue=[q for q,_ in pairs];keyed=[k for _,k in pairs]
    flagcounts=Counter(f['code'] for row in selected_audits for f in row['text_flags'])
    source={
        'generation_manifest_sha256':file_sha(Path(generation)/'manifest.json'),
        'generation_contract_sha256':file_sha(Path(generation)/'contract.json'),
        'source_journal_sha256':file_sha(Path(generation)/'journal.sqlite3') if (Path(generation)/'journal.sqlite3').is_file() else None,
        'generation_shards':{x['path']:x['sha256'] for x in manifest['shards']},
        'SFT_manifest_sha256':file_sha(Path(sft)/'manifest.json') if sft is not None else None,
        'tokenizer_meta_sha256':tokmeta,
    }
    stats={'status':'REVIEW_QUEUE_PREPARED','review_completed':False,
           'evidence_class':manifest['evidence_class'],
           'real_model_generated_corpus':manifest['evidence_class']=='MODEL_GENERATED',
           'model_behavior_validated_by_this_audit':False,
           'source':source,'generation_complete_records':len(records),
           'generation_mechanically_accepted':sum(x['mechanical_accepted'] for x in flags),
           'exportable_quartets':len(selected)//4,'review_queue_rows':len(selected),
           'reporting_by_frame':dict(Counter(k['frame'] for k in keyed)),
           'reporting_by_track':dict(Counter(k['track'] for k in keyed)),
           'origin_counts':dict(Counter(k['origin'] for k in keyed)),
           'unresolved_candidate_count':len(unknowned),'text_review_flags':dict(flagcounts),
           'near_duplicate_pairs':similarity_flags(selected),
           'unique_exact_rationales':len(unique_rationale),'tokenizer_counted_unique_rationale_tokens':tokens,
           'SFT_verified':export_check,'rubric':list(RUBRIC),
           'caveat':'The scanner catches explicit conflicts and supplies review work items. Mechanical acceptance and independent syntax checks cannot certify free-text reasoning; blind ratings must be completed and adjudicated.'}
    _jsonl(out/'review_queue.jsonl',queue)
    _jsonl(out/'blind_key.jsonl',keyed)
    _jsonl(out/'mechanical_audit.jsonl',flags)
    for reviewer in ('reviewer_A','reviewer_B'):
        template=[{'item_id':q['item_id'],'ratings':{k:None for k in RUBRIC},
                   'evidence_quotes':{},'comments':'','reviewer_id':'',
                   'reviewer_kind':'', 'submitted':False} for q in queue]
        _jsonl(out/f'{reviewer}_template.jsonl',template)
    write_json(out/'audit.json',stats)
    stats['outputs_sha256']={p.name:file_sha(p) for p in out.iterdir() if p.is_file() and p.name!='audit.json'}
    write_json(out/'audit.json',stats)
    return stats


def _load_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]


def validate_reviews(queue,reviews):
    ids={q['item_id'] for q in queue}
    if len(ids)!=len(queue) or len(reviews)!=len(queue):raise ValueError('incomplete review roster')
    if {r.get('item_id') for r in reviews}!=ids:raise ValueError('missing, unexpected or duplicate review ID')
    seen=set()
    by_id={q['item_id']:q for q in queue}
    for r in reviews:
        if r['item_id'] in seen:raise ValueError('duplicate review ID')
        seen.add(r['item_id'])
        if r.get('reviewer_kind') not in ('human','llm') or not r.get('reviewer_id') or r.get('submitted') is not True:
            raise ValueError('review provenance or submission missing')
        ratings=r.get('ratings',{})
        if set(ratings)!=set(RUBRIC) or any(type(v) is not int or v not in (0,1,2) for v in ratings.values()):
            raise ValueError('unscored rubric dimension')
        bad=[d for d in RUBRIC if ratings[d]!=2]
        quotes=r.get('evidence_quotes',{})
        if not isinstance(quotes,dict) or any(not isinstance(quotes.get(d),str) or not quotes[d].strip() for d in bad):
            raise ValueError('nonpassing ratings require evidence quotes')
        item=by_id[r['item_id']]
        source='\n'.join([item['context'],item['review_instruction'],
             *(str(v) for v in item['candidate'].values()),
             *(str(v) for v in item['counterfactual_operation'].values())])
        if any(quotes[d].strip() not in source for d in bad):
            raise ValueError('evidence quotes must appear verbatim in the review card')
    if len({r['reviewer_id'] for r in reviews})!=1 or len({r['reviewer_kind'] for r in reviews})!=1:
        raise ValueError('one reviewer per entire complete file')
    return True


def kappa(x,y):
    """Three-category unweighted Cohen kappa; undefined for constant matches."""
    if not x or len(x)!=len(y):raise ValueError('paired ratings required')
    observed=Fraction(sum(a==b for a,b in zip(x,y)),len(x))
    a=Counter(x);b=Counter(y);n=len(x)
    chance=sum(Fraction(a[i]*b[i],n*n) for i in range(3))
    return {'agreement':str(observed),'kappa':str((observed-chance)/(1-chance)) if chance!=1 else None}


def compile_reviews(audit_dir,review_a,review_b,out):
    if Path(out).exists():raise FileExistsError('fresh review report directory required')
    audit=Path(audit_dir)
    manifest=json.loads((audit/'audit.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='REVIEW_QUEUE_PREPARED':raise ValueError('review queue not certified')
    for filename,expected in manifest.get('outputs_sha256',{}).items():
        if Path(filename).name!=filename or file_sha(audit/filename)!=expected:
            raise ValueError('review source integrity mismatch: '+filename)
    if not manifest.get('outputs_sha256'):raise ValueError('missing source-hashed review roster')
    q=_load_jsonl(audit/'review_queue.jsonl')
    if len(q)!=manifest['review_queue_rows']:raise ValueError('audit roster cardinality mismatch')
    ra=_load_jsonl(review_a);rb=_load_jsonl(review_b)
    validate_reviews(q,ra);validate_reviews(q,rb)
    aa={r['item_id']:r for r in ra};bb={r['item_id']:r for r in rb}
    ia=ra[0];ib=rb[0]
    if ia['reviewer_id']==ib['reviewer_id']:
        raise ValueError('review files must come from distinct declared reviewers')
    by_dim={d:kappa([aa[x['item_id']]['ratings'][d] for x in q],[bb[x['item_id']]['ratings'][d] for x in q]) for d in RUBRIC}
    key=_load_jsonl(audit/'blind_key.jsonl')
    if len(key)!=len(q) or {r['item_id'] for r in key}!={r['item_id'] for r in q}:
        raise ValueError('review key does not match the blind roster')
    group_by_id={x['item_id']:x['group_id'] for x in key}
    all_motifs={x['group_id'] for x in key}
    disputed=[];confirmed=[];needs_adjudication=[]
    for item in q:
        rid=item['item_id'];a=aa[rid];b=bb[rid]
        mismatched=[d for d in RUBRIC if a['ratings'][d]!=b['ratings'][d]]
        nonpassing=[d for d in RUBRIC if min(a['ratings'][d],b['ratings'][d])<2]
        if mismatched or nonpassing:
            disputed.append({'item_id':rid,'different_scores':mismatched,'nonpassing':nonpassing})
            needs_adjudication.append(rid)
        else:confirmed.append(rid)
    affected_motifs=sorted({group_by_id[x] for x in needs_adjudication})
    clean_motifs=sorted(all_motifs-set(affected_motifs))
    allhuman=(ia['reviewer_kind']=='human' and ib['reviewer_kind']=='human')
    result={'status':'TWO_REVIEWER_TRIAGE_COMPLETE','reviewed_records':len(q),
            'reviewers':[{'id':ia['reviewer_id'],'kind':ia['reviewer_kind']},
                         {'id':ib['reviewer_id'],'kind':ib['reviewer_kind']}],
            'two_human_reviewers':allhuman,'agreement_by_dimension':by_dim,
            'unanimous_all_pass':len(confirmed),'records_for_adjudication':len(needs_adjudication),
            'adjudication_item_ids':needs_adjudication,'reviewer_disagreements':disputed,
            'motifs_requiring_adjudication':affected_motifs,
            'motifs_with_unanimous_all_pass':clean_motifs,
            'scholar_validation_completed':False,'public_release_approved':False,
            'model_SFT_training_approved_by_this_tool':False,
            'note':'Even unanimous reviews do not prove causal faithfulness; model-only reviewers give screening evidence. Training eligibility and public release require separate owner decisions.'}
    out=Path(out);out.mkdir(parents=True)
    write_json(out/'review_results.json',result)
    _jsonl(out/'adjudication_queue.jsonl',[q0 for q0 in q if q0['item_id'] in set(needs_adjudication)])
    return result
