# PrimeLab F04 bounded bring-up

This package freezes the candidate and execution contract for the first paid
PrimeLab action. It does not authorize billing by itself.

The selected candidate is one on-demand, secure-cloud A100 80 GB SXM4 virtual
machine from Massed Compute in the United States, with Ubuntu 22/CUDA 12,
16 vCPUs, 120 GB RAM, and a fixed 500 GB disk. The observed rate was $1.23 per
hour. Provisioning must fail closed above $1.30 per hour, after 0.5 billable
hours, or above $0.65 compute cost. Spot instances are forbidden.

After an exact source commit is pushed and the matching instance is
provisioned, the remote command is:

```bash
sudo bash scripts/stage_and_run_primelab_f04.sh \
  /path/to/ConstitutionalAlignment \
  <exact-source-commit> \
  /opt/jinn-f04/output
```

The staging phase installs the pinned direct dependencies and downloads the 12
files from the immutable Qwen revision. The probe then enters a Linux network
namespace with no external network, verifies every model byte, loads NF4,
runs deterministic thinking and non-thinking generations, records the actual
package lock, applies the 30-minute inference cap, and requires zero surviving
GPU compute processes.

The instance must be terminated immediately after the evidence is retrieved.
The final environment receipt is built with
`scripts/build_primelab_f04_receipt.py`; the factorization report must then be
regenerated before any curriculum generation or training is considered.
