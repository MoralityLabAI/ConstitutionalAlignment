# CPU evidence

`cpu_receipt.json` records the executed local Python 3.13.5 / PyTorch 2.10.0+cpu run: 65 tests, zero failures, zero skips, 640 deterministic fixture stage calls and 128 accepted fixture records. Its source hashes bind the tested Python files. The full log and reproducible data are available in the generated source/results archive; the CI workflow independently regenerates them and uploads its own evidence archive.

`fixture_sft_manifest.json` identifies four matched exports with 80 rows each, including common format warmups. They are synthetic fixtures and the production trainer rejects them. `scripted_scores.json` is a function check comparing an honest policy with a conservative policy. Neither is a trained model.

No pretrained teacher, student training, GPU inference, real-model activation experiment or Hugging Face upload was run for this local receipt. Gymnasium was absent locally; the dedicated CI workflow installs it and runs the optional environment checker as a separate step.
