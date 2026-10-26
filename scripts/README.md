# Scripts

Operational scripts. Everything that produces or moves results goes through the
`cotraffic` CLI; these are the file-level helpers around it.

| Script | What it does | Used by |
| --- | --- | --- |
| `export_dashboard_data.py` | Regenerate `frontend/public/data/*.json` from `results/` | `ARCHITECTURE.md` §5 runbook, dashboard |
| `record_replay.py` | Run one side-by-side episode and write the replay files | `POST /api/runs` |
| `reproduce_all.sh` | Full pipeline: networks → train/select → evaluate → figures → tables | reproduction |
| `open_in_sumo.py` | Open one episode in `sumo-gui` on its own | manual exploration |
| `merge_results.py` | Merge `results/raw` files produced on several machines | long training runs |
| `check_assistant.py` | Fixed question set through the assistant, with expected readings | assistant changes |
| `demo_side_by_side.py`, `demo_chart.py` | Two controllers on the same traffic, live chart | demos |

## explore/

One-off research helpers kept for provenance: they fetched OSM extracts and built the
earlier Monaco / Grand Tunis networks by hand. They are **not** part of any pipeline and
are not referenced by the CLI — `python -m cotraffic networks` builds networks from
`configs/networks/` instead. They are kept because they document where the source data
came from; delete them freely if the provenance stops mattering.
