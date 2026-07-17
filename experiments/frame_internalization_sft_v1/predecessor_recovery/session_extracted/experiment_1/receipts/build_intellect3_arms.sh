cd ~/.silico/libraries/goodfire-core && uv run python - <<'PY' 2>&1 | grep -v VIRTUAL_ENV
import os, json
from transformers import AutoTokenizer
ED=os.environ['SILICO_EXPERIMENT_DIR']
tok=AutoTokenizer.from_pretrained(os.environ['SILICO_EXPERIMENT_ARTIFACTS_DIR']+'/models/INTELLECT-3')
base=open(f"{ED}/prompts_built/base_think_informative.txt").read()
os.makedirs(f"{ED}/prompts_built/ab", exist_ok=True)
frames={"F0":None,"F1":"F1_constitutional.txt","F2":"F2_secular_auditor.txt","F3":"F3_eschatological.txt"}
manifest={"base":"base_think_informative.txt","base_tokens":len(tok(base)['input_ids']),"frames":{}}
for arm,fn in frames.items():
    if fn is None:
        sysp=base; ftok=0; ftext=""
    else:
        ftext=open(f"{ED}/frames/{fn}").read().strip()
        sysp=base+"\n\n"+ftext; ftok=len(tok(ftext)['input_ids'])
    open(f"{ED}/prompts_built/ab/system_{arm}.txt","w").write(sysp)
    manifest["frames"][arm]={"file":fn,"frame_tokens":ftok,"system_tokens":len(tok(sysp)['input_ids'])}
nz={a:m["frame_tokens"] for a,m in manifest["frames"].items() if m["frame_tokens"]>0}
lo,hi=min(nz.values()),max(nz.values()); manifest["frame_token_spread"]=round((hi-lo)/hi,4)
assert manifest["frame_token_spread"]<=0.10, manifest["frame_token_spread"]
json.dump(manifest,open(f"{ED}/frames/frames_manifest.json","w"),indent=2)
print(json.dumps(manifest,indent=2))
PY