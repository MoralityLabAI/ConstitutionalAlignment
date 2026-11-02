"""Reproduce source-bound CPU checks; fixture token lengths are never Qwen counts."""
from pathlib import Path
import json
import platform
import re
import subprocess
import sys
from .admission import write_json, implementation_hashes, hash_file, load_corpus, schedule
from .preflight import preflight
from .tests.test_training import FixtureTokenizer
from . import evaluation


def verify(out, regression_dir=None):
    out=Path(out)
    if out.exists():raise FileExistsError('fresh verification output required')
    out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[2]
    from ..ontological_constitution_v4.verify import verify_all
    if regression_dir is None:
        regression_dir=out/'regression'
        previous=verify_all(regression_dir)
    else:
        regression_dir=Path(regression_dir)
        previous=json.loads((regression_dir/'cpu_receipt.json').read_text())
        upstream=Path(__file__).resolve().parent.parent/'ontological_constitution_v4'
        if previous['status']!='CPU_VERIFIED' or previous['skipped_total']:
            raise ValueError('successful regression receipt required')
        if any(hash_file(upstream/name)!=value for name,value in previous['source_sha256'].items()):
            raise ValueError('regression source drift')
    import io, unittest
    from .tests import test_training
    stream=(out/'training_tests.log').open('w',encoding='utf-8',buffering=1)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_training))
    stream.close()
    if not result.wasSuccessful():raise RuntimeError((out/'training_tests.log').read_text()[-4000:])
    count=result.testsRun
    skipped_count=len(result.skipped)
    print('trainer suite complete', count, flush=True)
    report,_=preflight(regression_dir/'curriculum',FixtureTokenizer(),{'kind':'TEST_FIXTURE','name':'character-offset-contract-double'},
                       out/'fixture_preflight.json',max_length=32768)
    controls={}
    plan=evaluation.pair_plan()
    for policy in ('dutiful','always_positive','abandon','timeout'):
        controls[policy]=evaluation.run(plan,evaluation.d.scripted(policy),out/('control_'+policy))
    receipt={'status':'CPU_VERIFIED','python':platform.python_version(),'tests_total':previous['tests_total']+count,
        'new_tests':count,'regression_tests':previous['tests_total'],
        'skipped_total':previous['skipped_total']+skipped_count,
        'source_sha256':implementation_hashes(),'new_test_log_sha256':hash_file(out/'training_tests.log'),
        'admission':report['admission'],'paired_schedule':report['schedule'],
        'fixture_encoding_rows':sum(len(v) for v in report['per_row'].values()),
        'fixture_preflight_status':report['status'],'student_tokenizer_measurement':'NOT_RUN_TOKENIZER_NOT_MOUNTED',
        'tiny_torch_optimizer_tests':True,'transformers_peft_training_executed':False,
        'pretrained_weights_loaded':False,'gpu_jobs':0,'hub_uploads':0,'final_test_access':False,
        'controls':{k:{'records':v['records'],'paired_accuracy_bounds':v['paired_accuracy_bounds'],
                       'arms':v['arms']} for k,v in controls.items()}}
    write_json(out/'cpu_receipt.json',receipt)
    return receipt
