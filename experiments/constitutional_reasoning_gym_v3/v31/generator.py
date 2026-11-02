"""Adaptive, source-checked generation with selective legacy repair.

The v3.0 five-stage generator remains immutable. Existing v3.0 canary shards
and partial journal calls are read-only inputs to this new v3.1 batch.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
from sqlite3 import connect
import gzip
import json
import time
from .. import data as v3
from ..core import FRAMES, TENETS, case_dict, case_from, canon, file_sha, sha, write_json
from .audit import audit_candidate, correction_targets
from . import VERSION


class LegacySource:
    def __init__(self, root=None):
        self.root=Path(root) if root is not None else None
        self.records={};self.meta=None;self.db=None
        if self.root is None:return
        manifest=self.root/'manifest.json';contract=self.root/'contract.json'
        if not manifest.is_file() or not contract.is_file():raise ValueError('legacy manifest and contract required')
        m=json.loads(manifest.read_text(encoding='utf-8'))
        co=json.loads(contract.read_text(encoding='utf-8'))
        if m.get('contract_sha256')!=sha(co):
            raise ValueError('legacy contract hash mismatch')
        if co.get('scenario_split')!='train' or co.get('schema')!='ca-gym-v3-generation-v1' or m.get('final_test_access') is not False:
            raise ValueError('legacy corpus is not certified train-only v3.0 data')
        for r in v3.read_records(self.root):
            c=case_from(r['case'])
            if c.split!='train' or r['split']!='train' or not r['training_eligible'] or r['frame'] not in FRAMES:
                raise ValueError('legacy evaluation contamination')
            key=(c.case_id,r['frame'])
            if key in self.records:raise ValueError('duplicated legacy record')
            self.records[key]=r
        journal=self.root/'journal.sqlite3'
        if journal.exists():
            self.db=connect(f'file:{journal}?mode=ro',uri=True)
        self.meta={'manifest_sha256':file_sha(manifest),'contract_sha256':file_sha(contract),
                   'source_shards':{s['path']:s['sha256'] for s in m.get('shards',[])},
                   'journal_sha256':file_sha(journal) if journal.exists() else None,
                   'source_teacher':m.get('teacher'),'source_seed':co.get('seed'),
                   'source_assigned_groups':co.get('groups'),
                   'source_completed_records':m.get('completed_records'),
                   'original_generation_schema':co.get('schema'),
                   'imported_original_source_revision':co.get('source_revision'),
                   'source_final_test_access':False}

    def recover(self,c,frame,mode):
        """Recover an intact completed row or additional partial journal stages.

        The partial journal is queried by original v3 request IDs, never edited.
        Every returned original response and complete request is preserved.
        """
        key=(c.case_id,frame)
        if key in self.records:
            r=self.records[key]
            if r['mode']!=mode or canon(r['case'])!=canon(case_dict(c)):
                raise ValueError('legacy record differs from frozen v3 assignment')
            history=r['revision_history']
            if not history or history[-1]['response']!=r['rewrite']:
                raise ValueError('legacy revision history integrity')
            selected,response=self._choose_saved(c,history)
            origin='LEGACY_COMPLETED_ROW' if selected==len(history)-1 else 'LEGACY_RECOVERED_EARLIER_STAGE'
            return {'response':response,'origin':origin,'selected_index':selected,
                    'history':history,'draft':r['draft'],
                    'old_record_id':r['record_id']}
        if self.db is None:return None
        history=[];draft=None;previous=None
        co=json.loads((self.root/'contract.json').read_text(encoding='utf-8'))
        for round_index in range(0,int(co.get('rewrite_rounds',1))+1):
            if round_index==0:
                req=v3.request(c,frame,mode,'draft')
                result=self._journal_lookup(req)
                if result is None:return None
                history.append({'stage':'draft','request':req,'response':result})
                draft=result;previous=result
                continue
            cq=v3.request(c,frame,mode,'critique',previous['text'],round_index=round_index)
            critique=self._journal_lookup(cq)
            if critique is None:break
            history.append({'stage':'critique','request':cq,'response':critique})
            rq=v3.request(c,frame,mode,'rewrite',previous['text'],critique['text'],round_index)
            response=self._journal_lookup(rq)
            if response is None:break
            history.append({'stage':'rewrite','request':rq,'response':response})
            previous=response
        selected,response=self._choose_saved(c,history)
        return {'response':response,'origin':'LEGACY_PARTIAL_JOURNAL',
                'selected_index':selected,'history':history,'draft':draft,'old_record_id':None}

    @staticmethod
    def _choose_saved(case,history):
        # A five-stage v3.0 run sometimes regressed on a later rewrite. The
        # latest previously *accepted* candidate is recoverable at zero GPU cost.
        # Source stages and unselected alternatives remain in the raw archive.
        candidates=[(i,h['response']) for i,h in enumerate(history)
                    if h['stage'] in ('draft','rewrite')]
        accepted=[(i,r) for i,r in candidates if audit_candidate(case,r['text'])['accepted']]
        return accepted[-1] if accepted else candidates[-1]

    def _journal_lookup(self,req):
        row=self.db.execute('SELECT request,result FROM calls WHERE id=?',(req['request_id'],)).fetchone()
        if row is None:return None
        if row[0]!=canon(req):raise ValueError('legacy journal request collision')
        result=json.loads(row[1])
        if not isinstance(result.get('text'),str):raise ValueError('legacy journal output invalid')
        return result

    def close(self):
        if self.db is not None:self.db.close()


def build_request(case,frame,mode,stage,prior=None,audit=None,round_index=0):
    if case.split!='train' or frame not in FRAMES or mode not in v3.MODES:
        raise ValueError('only train cases and declared frames are allowed')
    if stage not in ('draft','targeted_repair'):
        raise ValueError('unknown v3.1 generation stage')
    guide=('Return one JSON object with exactly these fields: choice (integer 0..2), '
           'counterfactual_choice (integer 0..2), evidence_ids (every supplied fact ID exactly once), '
           'tenets (1..3 recognized IDs), rationale (30..260 words of public deliberation). '
           'Explain the pivotal authenticated fact, state its Boolean truth value, name the strongest counterpressure, '
           'and explain a constructive alternative. ALL listed facts have authenticated provenance, '
           'including facts whose authenticated_value is false. A false authenticated fact is an authenticated negative. '
           'Invert only the pivotal fact for the counterfactual; use the numeric action mapping. '
           'Never invent a scripture citation or external evidence.')
    system=FRAMES[frame]+'\nTenets: '+canon(v3.CONSTITUTION)
    base=v3.user_context(case,mode)
    if stage=='draft':
        prompt=base+'\n'+guide
    else:
        if not isinstance(prior,str) or audit is None:raise ValueError('targeted repair requires an audited candidate')
        targets=correction_targets(case,audit)
        prompt=(base+'\nFAILED_CANDIDATE\n'+prior+'\nDETERMINISTIC_VERIFIER_FEEDBACK\n'+canon(targets)
                +'\nRewrite the entire response, correcting each listed error. '+guide)
    body={'schema':'ca-gym-v3.1-request-v1','case':case_dict(case),'frame':frame,'mode':mode,
          'stage':stage,'round':round_index,
          'messages':[{'role':'system','content':system},{'role':'user','content':prompt}]}
    body['request_id']=sha(body)
    return body


def _write_shard(path,records):
    payload=''.join(canon(r)+'\n' for r in records).encode('utf-8')
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_bytes(gzip.compress(payload,mtime=0));tmp.replace(path)
    return {'path':path.name,'rows':len(records),'sha256':file_sha(path)}


def planned_jobs(groups,seed,start_group=0):
    if type(start_group) is not int or start_group<0 or groups+start_group>100000:
        raise ValueError('invalid range of training motifs')
    # Deterministic index window. Separate H100 batches with disjoint indices
    # cannot reproduce each other's source motifs accidentally.
    cases=list(v3.training_cases(groups+start_group,seed))
    return [(c,f,v3.MODES[int(c.group_id[:8],16)%3])
            for c in cases[start_group*2:] for f in FRAMES]


def export_v31(source,target,allow_fixture=False):
    """Re-audit every exported source row; use the original paired v3.0 exporter.

    Keeps existing SFT field semantics, output names, masked rationale and
    natural EOS contract while adding the v3.1 polarity and provenance checks.
    """
    from ..data import read_records,export_sft
    for record in read_records(source):
        if record.get('v31_version')!=VERSION or record.get('split')!='train':
            raise ValueError('only versioned v3.1 training records')
        c=case_from(record['case'])
        a=audit_candidate(c,record['rewrite']['text'])
        if a['accepted']!=record['rewrite_audit']['accepted'] or a['errors']!=record['rewrite_audit']['errors']:
            raise ValueError('v3.1 audit drift')
    result=export_sft(source,target,allow_fixture=allow_fixture)
    result['source_v31']=VERSION
    result['free_text_semantics_verified']=False
    result['human_semantic_review_required']=True
    result['accepted_polarity_screened']=True
    write_json(Path(target)/'manifest.json',result)
    return result


def produce_adaptive(teacher,out,groups=16,seed=41,batch_size=4,seconds=900,
                     token_cap=500000,max_new_tokens=768,max_repairs=2,legacy_root=None,
                     start_group=0):
    if not 1<=groups<=100000 or type(start_group) is not int or start_group<0 or start_group+groups>100000 or not 1<=batch_size<=64 or not 0<=max_repairs<=3 or seconds<=0 or token_cap<=0:
        raise ValueError('invalid capacity or retry arguments')
    out=Path(out)
    if legacy_root is not None and (out.resolve()==Path(legacy_root).resolve() or
                                    out.resolve().is_relative_to(Path(legacy_root).resolve())):
        raise ValueError('v3.1 output must not overwrite or nest inside legacy source')
    out.mkdir(parents=True,exist_ok=True)
    legacy=LegacySource(legacy_root)
    try:
        desc=teacher.describe()
        if legacy.meta is not None and legacy.meta['source_seed']!=seed:
            raise ValueError('legacy generation seed differs from v3.1 assignment')
        if desc.get('evidence_class') not in ('MODEL_GENERATED','SYNTHETIC_FIXTURE'):
            raise ValueError('unrecognized teacher evidence class')
        # New synthetic fixture rows cannot be mixed into an earlier model run.
        if legacy.meta is not None and desc['evidence_class']!=legacy.meta['source_teacher'].get('evidence_class'):
            raise ValueError('teacher evidence class mismatches legacy source')
        package=Path(__file__).resolve().parent
        contract={'schema':VERSION,'teacher':desc,'groups':groups,'seed':seed,'batch_size':batch_size,
                  'seconds':seconds,'token_cap':token_cap,'max_new_tokens':max_new_tokens,
                  'max_repairs':max_repairs,'legacy':legacy.meta,
                  'upstream_source':'ca-gym-v3.0.0','split':'train','test_access':False,
                  'implementation_sha256':{p.relative_to(package).as_posix():file_sha(p)
                      for p in sorted(package.rglob('*.py')) if '__pycache__' not in p.parts}}
        cp=out/'contract.json'
        if cp.exists() and json.loads(cp.read_text(encoding='utf-8'))!=contract:
            raise ValueError('existing run contract differs; use a fresh output directory')
        write_json(cp,contract)
        journal=v3.Journal(out/'journal.sqlite3')
        start=time.monotonic();new_calls=0;records=[];status='COMPLETE';reason=None
        jobs=planned_jobs(groups,seed,start_group)
        def obtain(reqs):
            nonlocal new_calls
            missing=[rq for rq in reqs if journal.get(rq) is None]
            if missing:
                if time.monotonic()-start>=seconds:
                    raise TimeoutError('internal generation deadline')
                if desc['evidence_class']=='MODEL_GENERATED' and journal.tokens()+len(missing)*max_new_tokens>token_cap:
                    raise TimeoutError('reserved maximum output tokens exceed remaining budget')
                outputs=teacher.generate_many(missing)
                if len(outputs)!=len(missing):raise ValueError('backend response cardinality')
                for rq,resp in zip(missing,outputs):
                    if not isinstance(resp.get('text'),str):raise ValueError('missing raw output')
                    if desc['evidence_class']=='MODEL_GENERATED':
                        n=resp.get('output_tokens')
                        if type(n) is not int or not 0<=n<=max_new_tokens:
                            raise ValueError('unaccounted output token count')
                        if 'raw_generated_token_ids' in resp:
                            ids=resp['raw_generated_token_ids']
                            if not isinstance(ids,list) or len(ids)!=n or any(type(t) is not int for t in ids):
                                raise ValueError('generated token IDs disagree with token count')
                    journal.put(rq,resp);new_calls+=1
            return [journal.get(rq) for rq in reqs]
        try:
            for start_index in range(0,len(jobs),batch_size):
                chunk=jobs[start_index:start_index+batch_size]
                states=[];draft_requests=[]
                for c,f,m in chunk:
                    original=legacy.recover(c,f,m)
                    state={'case':c,'frame':f,'mode':m,'import':original,'history':list(original['history']) if original else [],
                           'origin':original['origin'] if original else 'V31_NEW',
                           'attempts':[]}
                    if original:
                        state['current']=original['response']
                    else:
                        rq=build_request(c,f,m,'draft')
                        state['initial_request']=rq;draft_requests.append(rq)
                    states.append(state)
                draft_results={rq['request_id']:val for rq,val in zip(draft_requests,obtain(draft_requests))}
                for state in states:
                    if 'initial_request' in state:
                        rq=state.pop('initial_request');state['current']=draft_results[rq['request_id']]
                        state['history'].append({'stage':'draft','request':rq,'response':state['current']})
                    state['draft_audit_v31']=audit_candidate(state['case'],state['history'][0]['response']['text'])
                    state['audit']=audit_candidate(state['case'],state['current']['text'])
                for ri in range(1,max_repairs+1):
                    pending=[state for state in states if not state['audit']['accepted']]
                    if not pending:break
                    repairs=[build_request(s['case'],s['frame'],s['mode'],'targeted_repair',
                                           s['current']['text'],s['audit'],ri) for s in pending]
                    replies=obtain(repairs)
                    for state,rq,resp in zip(pending,repairs,replies):
                        state['attempts'].append({'before_error_codes':state['audit']['errors'],
                                                  'request_id':rq['request_id']})
                        state['history'].append({'stage':'targeted_repair','request':rq,'response':resp})
                        state['current']=resp
                        state['audit']=audit_candidate(state['case'],resp['text'])
                        state['attempts'][-1]['after_error_codes']=state['audit']['errors']
                for state in states:
                    c,f,m=state['case'],state['frame'],state['mode']
                    hist=state['history'];draft=state['import']['draft'] if state['import'] else hist[0]['response']
                    # Preserve audit feedback as a deterministic machine critique, without
                    # pretending the model generated a second critique stage.
                    critique={'text':canon({'deterministic_verifier_errors':state['draft_audit_v31']['errors']}),
                              'source':'v31_exact_oracle_and_polarity_screen'}
                    record={'record_id':sha([c.case_id,f,m]),'case':case_dict(c),'frame':f,'mode':m,
                         'training_eligible':True,'split':'train','group_id':c.group_id,
                         'v31_version':VERSION,'origin':state['origin'],
                         'legacy_original_record_id':state['import']['old_record_id'] if state['import'] else None,
                         'legacy_selected_stage_index':state['import']['selected_index'] if state['import'] else None,
                         'draft':draft,'critique':critique,'rewrite':state['current'],
                         'request_ids':[x['request']['request_id'] for x in hist],
                         'requests':[x['request'] for x in hist],'revision_history':hist,
                         'v31_attempts':state['attempts'],'student_prompt':v3.user_context(c,m),
                         'frame_text':FRAMES[f],'draft_audit':state['draft_audit_v31'],
                         'rewrite_audit':state['audit'],'evidence_class':desc['evidence_class']}
                    records.append(record)
        except TimeoutError as exc:
            status='PARTIAL';reason=str(exc)
        except (RuntimeError,MemoryError) as exc:
            status='ABORTED';reason=type(exc).__name__+': '+str(exc)
        finally:
            calls,tokens=journal.count(),journal.tokens()
            journal.close()
        shards=out/'shards';shards.mkdir(exist_ok=True)
        entries=[_write_shard(shards/f'raw-{i//128:05}.jsonl.gz',records[i:i+128])
                  for i in range(0,len(records),128)]
        accepted=[r for r in records if r['rewrite_audit']['accepted']]
        grouped=defaultdict(dict)
        for r in records:
            key=(r['group_id'],r['case']['authorized']);grouped[key][r['frame']]=r
        complete_pairs=[gid for gid in sorted({r['group_id'] for r in records})
                        if all((gid,authorized) in grouped and set(grouped[(gid,authorized)])==set(FRAMES)
                               and all(x['rewrite_audit']['accepted'] for x in grouped[(gid,authorized)].values())
                               for authorized in (False,True))]
        errors=Counter(e for r in records if not r['rewrite_audit']['accepted'] for e in r['rewrite_audit']['errors'])
        origins=Counter(r['origin'] for r in records)
        per_track={name:{'complete':sum(r['case']['track']==name for r in records),
                         'accepted':sum(r['case']['track']==name and r['rewrite_audit']['accepted'] for r in records)}
                   for name in v3.TRACKS}
        per_frame={name:{'complete':sum(r['frame']==name for r in records),
                         'accepted':sum(r['frame']==name and r['rewrite_audit']['accepted'] for r in records)}
                   for name in FRAMES}
        # Reason word counts are descriptive; only a pinned tokenizer can report tokens.
        distinct={sha(r['rewrite_audit']['parsed']['rationale']):r['rewrite_audit']['parsed']['rationale']
                  for r in accepted}
        manifest={'status':status,'reason':reason,'v31_version':VERSION,'contract_sha256':sha(contract),
                  'start_group':start_group,'end_group_exclusive':start_group+groups,
                  'teacher':desc,'completed_records':len(records),'planned_records':len(jobs),
                  'accepted_rewrites':len(accepted),'paired_accepted_motifs':len(complete_pairs),
                  'paired_motif_ids':complete_pairs,'calls_total':calls,'new_calls':new_calls,
                  'actual_output_tokens':tokens,'distinct_accepted_reason_texts':len(distinct),
                  'distinct_accepted_reason_words':sum(len(t.split()) for t in distinct.values()),
                  'tokenizer_counted_accepted_tokens':None,'actual_billed_gpu_minutes':None,
                  'origin_counts':dict(origins),'repaired_records':sum(bool(r['v31_attempts']) for r in records),
                  'draft_accepted':sum(r['draft_audit']['accepted'] for r in records),
                  'repair_successes':sum(not r['draft_audit']['accepted'] and r['rewrite_audit']['accepted'] for r in records),
                  'new_targeted_repair_successes':sum(bool(r['v31_attempts']) and r['rewrite_audit']['accepted'] for r in records),
                  'repair_regressions':sum(r['draft_audit']['accepted'] and not r['rewrite_audit']['accepted'] for r in records),
                  'unresolved_error_codes':dict(errors),'by_track':per_track,'by_frame':per_frame,
                  'elapsed_seconds':round(time.monotonic()-start,3),'shards':entries,
                  'legacy_source':legacy.meta,'free_text_semantics_verified':False,
                  'human_semantic_review_required':True,'evidence_class':desc['evidence_class'],
                  'final_test_access':False,'paid_gpu_jobs_launched_by_this_code':0}
        write_json(out/'manifest.json',manifest)
        return manifest
    finally:legacy.close()
