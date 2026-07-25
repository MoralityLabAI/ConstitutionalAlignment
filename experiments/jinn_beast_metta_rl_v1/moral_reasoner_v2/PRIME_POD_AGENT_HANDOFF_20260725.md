# Prime pod operator handoff

Prepared 2026-07-25 for a second agent operating the existing
`moralitylab` Prime Intellect account. This handoff delegates a bounded pod
bring-up; it does not authorize another hosted RL run, an eight-GPU cluster, or
changes to the frozen Jinn moral-reasoner experiment.

## Active session and protected run

- Prime account username: `moralitylab`
- Prime user ID: `cmbqxo1kc0020eppjy9mnws3d`
- Active hosted RL run: `e2s64hw5ywag1d8hgwfef6jd`
- Run name: `jinn-moral-reasoner-qwen35-4b-thinking-v2`
- Environment: `moralitylab/jinn-beast-metta:0.1.9`
- Environment version ID: `yz0iwzj2xl6f762zrastkw1j`

The RL run was active when this handoff was written. Recheck it before pod
creation. Do not stop, relaunch, duplicate, mutate, or attach resources to that
run. The pod is a separate compute lane.

No credential is stored in this repository. Use the already authenticated
Prime CLI profile on this Windows account. Stop immediately if `whoami` does
not resolve to the username and user ID above.

## Delegated launch envelope

The operator may create at most one pod at a time under all of these limits:

- exactly one `A100_80GB`;
- listed price no greater than USD 0.70 per GPU-hour;
- maximum planned lifetime of two hours;
- no spot instance unless interruption is acceptable for the named task;
- no additional hosted RL run and no local GPU workload;
- no secrets passed through `--env` or committed to the repository;
- terminate the pod immediately after artifacts are copied and verified.

If no matching configuration is in stock, record the availability response and
stop. Do not silently substitute a different GPU, increase GPU count, or exceed
the price or time limits.

Before creation, write the intended task, selected availability ID, provider,
region, listed hourly price, image, disk size, and expected output path into a
new receipt beside this file. The pod name must start with
`jinn-paper-20260725-` and identify the task.

## Windows CLI entry

The top-level Prime executable imports a POSIX-only module on this machine.
Invoke the installed command apps directly:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PRIME_DISABLE_VERSION_CHECK = '1'
$primePython = 'C:\Users\patri\AppData\Roaming\uv\tools\prime\Scripts\python.exe'

& $primePython -c "from prime_cli.commands.whoami import app; app()" --plain
& $primePython -c "from prime_cli.commands.pods import app; app()" list --output json --plain
& $primePython -c "from prime_cli.commands.rl import app; app()" get e2s64hw5ywag1d8hgwfef6jd --output json --plain
& $primePython -c "from prime_cli.commands.availability import app; app()" list --gpu-type A100_80GB --gpu-count 1 --output json --plain
```

Select only an availability row satisfying the launch envelope. Use its exact
opaque `id`; do not derive or reformat it:

```powershell
& $primePython -c "from prime_cli.commands.pods import app; app()" create `
  --id '<EXACT_AVAILABILITY_ID>' `
  --name 'jinn-paper-20260725-<TASK>' `
  --gpu-count 1 `
  --disk-size <GB> `
  --image '<IMAGE>' `
  --yes `
  --plain
```

Record the returned pod ID before doing anything else. Verify installation and
GPU topology:

```powershell
& $primePython -c "from prime_cli.commands.pods import app; app()" status <POD_ID> --output json --plain
```

Use `pods connect` or `pods ssh` only after status reports a ready installation.
Do not use the repository's Windows tunnel shim for a tunnel command.

## Required closeout

Copy only task artifacts and non-secret logs back to the experiment packet,
hash them, then terminate the exact recorded pod ID:

```powershell
& $primePython -c "from prime_cli.commands.pods import app; app()" terminate <POD_ID> --yes --plain
& $primePython -c "from prime_cli.commands.pods import app; app()" list --output json --plain
& $primePython -c "from prime_cli.commands.pods import app; app()" history --output json --plain
```

The closeout receipt must contain:

- pod ID, availability ID, provider, region, GPU type/count, and image;
- creation, ready, workload-start, workload-end, and termination timestamps;
- listed hourly price, elapsed hours, and estimated total cost;
- exact command or launcher revision used;
- artifact paths and SHA-256 digests;
- final pod status and confirmation that no pod remains active;
- the contemporaneous status of protected RL run
  `e2s64hw5ywag1d8hgwfef6jd`.

Pod creation is infrastructure authorization only. It does not promote any
behavioral result or relax the prospective analysis gates.
