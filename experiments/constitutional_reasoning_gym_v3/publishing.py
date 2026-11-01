"""Private, versioned training bundle with a distinct raw-audit archive."""
from __future__ import annotations
from pathlib import Path
import json
import shutil
from .core import file_sha,write_json,sha


def prepare_bundle(sft_dir,out,generation_dir=None):
    source=Path(sft_dir);out=Path(out)
    if out.exists():raise ValueError('new bundle directory required')
    report=json.loads((source/'manifest.json').read_text())
    if report.get('fixture_only') or report.get('status')!='SFT_EXPORT_READY':
        raise ValueError('publishable bundle requires generated accepted data')
    if generation_dir is None:raise ValueError('raw generation directory required for full provenance')
    from .data import read_records
    generation=Path(generation_dir);gm=json.loads((generation/'manifest.json').read_text())
    records=list(read_records(generation))
    if not records or any(r['evidence_class']!='MODEL_GENERATED' or r['split']!='train' for r in records):
        raise ValueError('raw archive must be model-generated train data')
    request_ids={rq['request_id'] for r in records for rq in r['requests']}
    out.mkdir(parents=True);files={};data_files={}
    for name,meta in report['arms'].items():
        p=source/f'{name}.jsonl'
        if file_sha(p)!=meta['sha256']:raise ValueError('SFT source integrity')
        for line in p.read_text().splitlines():
            row=json.loads(line)
            if row['split']!='train' or row['source_evidence_class']!='MODEL_GENERATED':raise ValueError('eval/fixture contamination')
            if not set(row['source_request_ids'])<=request_ids:raise ValueError('generation lineage missing')
        shutil.copyfile(p,out/p.name);files[p.name]=meta['sha256'];data_files[p.name]=meta['sha256']
    (out/'raw').mkdir()
    for name in ('contract.json','manifest.json'):
        shutil.copyfile(generation/name,out/'raw'/name);files['raw/'+name]=file_sha(out/'raw'/name)
    for item in gm['shards']:
        name=item['path'];shutil.copyfile(generation/'shards'/name,out/'raw'/name)
        files['raw/'+name]=file_sha(out/'raw'/name)
    batch=sha({'source':report,'generation_contract':gm['contract_sha256']})[:24]
    manifest={'schema':'ca-gym-v3-hub-v2','private':True,'batch_id':batch,'files':files,
              'training_data_files':data_files,'source_manifest':report,
              'public_release':'separate owner license/provenance review',
              'evaluation_included':False,'raw_full_requests_included':True,
              'raw_archive_is_not_a_training_split':True}
    write_json(out/'manifest.json',manifest)
    card='''---
language:
- en
license: other
license_name: upstream-and-generated-data-terms-pending-review
task_categories:
- text-generation
tags:
- synthetic
- constitutional-alignment
- research
---
# Constitutional reasoning gym v3

Private working batch of model-generated public explanations and numeric actions.
Use only the files enumerated in `training_data_files` for training. The separate
`raw/` archive retains complete prompts and draft/critique/rewrite outputs, including
rejected candidates, for auditing. It must not be loaded as SFT examples.

Every row carries a scenario group and generation lineage. Only training scenarios
are included. Curricula vary constitutional framing and rationale-loss masking.
Verified task actions do not certify free-text reasoning faithfulness.

Review teacher provenance and licenses before public release. This batch contains
no Jinn or Beast holdout traces, private manuscript text, or evaluation keys.
'''
    (out/'README.md').write_text(card,encoding='utf-8')
    return manifest


def publish_private(bundle,repo_id,approved=False):
    if not approved:raise PermissionError('Hub write requires owner approval')
    if repo_id.count('/')!=1 or '..' in repo_id:raise ValueError('owner/dataset required')
    root=Path(bundle);m=json.loads((root/'manifest.json').read_text())
    if m.get('private') is not True or m.get('evaluation_included') is not False:raise ValueError('private training-only contract')
    for name,expected in m['files'].items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or file_sha(root/rel)!=expected:raise ValueError('bundle integrity')
    from huggingface_hub import HfApi
    api=HfApi();api.create_repo(repo_id,repo_type='dataset',private=True,exist_ok=True)
    if not api.repo_info(repo_id,repo_type='dataset').private:raise ValueError('destination exists publicly; refusing upload')
    prefix='batches/'+m['batch_id']
    commit=api.upload_folder(repo_id=repo_id,repo_type='dataset',folder_path=str(root),path_in_repo=prefix,
               allow_patterns=[*m['files'],'manifest.json','README.md'],commit_message='Add audited v3 training batch '+m['batch_id'])
    receipt={'repo_id':repo_id,'private':True,'path':prefix,'commit':commit.oid,'batch_id':m['batch_id']}
    write_json(root/'upload_receipt.json',receipt)
    return receipt
