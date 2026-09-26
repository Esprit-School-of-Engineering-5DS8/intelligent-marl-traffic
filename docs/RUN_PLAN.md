# Run plan

Every long job is one command, resumable, and writes its own files, so the work can be
split between laptops, Kaggle and Colab and merged afterwards.

## 1. Setup (once per machine)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt && pip install -e . --no-deps
python -m cotraffic smoke                                # a few minutes, must end with 0 failures
```

## 2. Training jobs

One job = one variant x one network x one training seed. On the team laptop (i5-1135G7,
single thread) a grid4x4 job of 500 000 agent steps takes about 15-20 min; see the journal
for measured times. Jobs resume from their latest checkpoint if interrupted.

| Variant | grid4x4 seeds | real_district seeds |
|---|---|---|
| ind | 1, 2, 3 | 1, 2, 3 |
| coop | 1, 2, 3 | 1, 2, 3 |
| coop_eco05 | 1, 2, 3 | - |
| coop_eco | 1, 2, 3 | - |
| coop_full | 1, 2, 3 | 1, 2, 3 |
| coop_forecast | 1, 2, 3 | - |
| coop_full_ev1, coop_full_ev4 | 1 | - |

```bash
python -m cotraffic train --agent coop --net grid4x4 --seed 1      # or: make train AGENT=coop NET=grid4x4 SEED=1
```

On Kaggle / Colab: `notebooks/kaggle_train.ipynb`, `notebooks/colab_train.ipynb` (same
command; checkpoints saved to the notebook output or to Google Drive).

After training, pick the checkpoint of each run on validation seeds (never on test seeds):

```bash
python -m cotraffic select --jobs 2            # all runs found under results/training
```

Selected checkpoints go to `results/checkpoints/<variant>/<network>/seed<k>.zip` (+ .json
with the validation scores). Copy those folders between machines.

## 3. Evaluation

```bash
python -m cotraffic evaluate --experiment core --jobs 2        # RQ1-RQ5, run on the team laptop
python -m cotraffic evaluate --experiment extended --jobs 2    # rest of the design (other machines)
python -m cotraffic evaluate --experiment full_matrix --jobs 2 # both at once
python -m cotraffic evaluate --experiment sensitivity --jobs 2 # forecast block, EV weight
```

`core` is 790 runs, `extended` 420 (learned variants: 3 training seeds x 5 evaluation seeds
per cell). Measured cost on the laptop with 2-5 processes sharing it: 0.5-2 min per run,
except peak demand with the SSM device (about 5 min) and grid8x8 (about 4 min).

Runs with a result file are skipped, so the same command completes an interrupted matrix.
To split the matrix: run subsets with `--methods ...` on different machines, then merge:

```bash
python scripts/merge_results.py /path/to/other/results/raw
```

## 4. Analysis

```bash
python -m cotraffic aggregate      # results/summary/*.csv (means, CIs, tests)
python -m cotraffic figures        # figures/*.png|svg
python -m cotraffic tables         # results/summary/REPORT_TABLES.md
```
