# D1 report material

Shared folder for the 3–4 page D1 PDF. Each member adds their section and figures here, and
one person merges them into the PDF.

| File | Owner | What |
|---|---|---|
| `D1_remaining.md` | all | **What's left for D1, per member** (start here) |
| `nayab_part.md` | Member 1 | Data sources, preprocessing, validation, DVC/DagsHub, Prefect + monitoring |
| `dvc_dag.png` | Member 1 | `dvc dag` output (required screenshot) |
| `dvc_dag.txt` / `dvc_dag.md` | Member 1 | Same graph as plain text / Mermaid |
| *(Member 2)* | Member 2 | Models, metrics, ≥2 MLflow runs screenshot, registered model in **Staging** screenshot |
| *(Member 3)* | Member 3 | API/deployment section; **compiles the PDF**, README pass, CI green |

Required in the PDF (from the D1 brief): repo + DagsHub/MLflow links, screenshots of ≥2 MLflow
runs, the registered model in Staging/Production, and `dvc dag`.

To regenerate the DAG text: `dvc dag > docs/report/dvc_dag.txt` (Mermaid: `dvc dag --md`).
