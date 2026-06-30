# Project Context

## Purpose

`sleap-roots-pipeline` is the **orchestration layer** for the sleap-roots plant-root
phenotyping pipeline. It declares how three containerized stages are wired together and
scheduled on a GPU cluster:

1. **models-downloader** — prepares SLEAP model files for inference
2. **predictor** — runs SLEAP predictions on input image sets (GPU)
3. **trait-extractor** — extracts phenotypic traits from the predictions

This repo holds **no application/library code of its own** — it is the declarative glue
(Argo `Workflow` + `WorkflowTemplate` manifests and shell launchers) that runs images
built and published by the sibling service repos (`models-downloader`,
`sleap-roots-predict`, `sleap-roots` trait-extractor).

The roadmap target (see `docs/bloom-integration/roadmap.md`, tier **A4**) is to evolve
this from a manually-launched batch pipeline into **event-driven, per-scan orchestration**:
a scan ingested into Bloom triggers a per-scan Argo workflow (predict → traits →
write-back with provenance) via Argo Events. That A4 design is **out of scope here** —
this repo is currently at the **A0 tooling-baseline** stage (OpenSpec + canonical Claude
commands).

## Tech Stack

- **Argo Workflows** — DAG orchestration (`sleap-roots-pipeline.yaml` entrypoint +
  `*-template.yaml` `WorkflowTemplate`s referenced via `templateRef`)
- **Argo Events** — (planned, A4) scan-ingest → workflow trigger
- **RunAI** — GPU scheduling on the `runai-talmo-lab` namespace (fractional GPU via
  `gpu-fraction`, `preemptible`, `project` labels for quota)
- **Kubernetes** — execution substrate; `hostPath` / PV+PVC volumes for model/image/output
  mounts; `nvidia.com/gpu` resource limits
- **Bash** — launchers (`runai_run_pipeline.sh` for the cluster,
  `local_run_pipeline_first_time.sh` for local Docker Desktop + WSL2 testing)
- **Docker / GHCR** — stage images are built in their own repos and *consumed* here

No Python package, no Node package, no build step, and (currently) no CI — the artifacts
are YAML manifests and shell scripts.

## Project Conventions

### Code Style

- **Declarative YAML first.** Orchestration logic lives in Argo manifests, not imperative
  scripts. Keep `WorkflowTemplate`s small, named, and reusable; the top-level `Workflow`
  wires them with `templateRef` + `dependencies`.
- **Cluster vs. local parity.** Cluster manifests are the canonical set; the
  `local-WSL2-*.yaml` / `local-*.yaml` variants mirror them for Docker Desktop + WSL2
  testing. When you change one, check the other for drift.
- **Pin images by tag/digest**, never `:latest`, so a run is reproducible.
- Shell scripts should be safe (`set -euo pipefail`) and must never echo `ARGO_TOKEN` or
  other secrets.

### Architecture Patterns

- **Three-stage DAG**: models-downloader → predictor → trait-extractor, with
  `dependencies:` enforcing order and `retryStrategy` handling preemption/transient
  failures.
- **Templates are versioned, shared building blocks** (`argo template create …`), referenced
  by the workflow rather than inlined.
- **Storage is mount-based**: model input, image input, and outputs are passed between
  stages via mounted volumes (`hostPath type: Directory` locally; PV/PVC on cluster). A
  missing `hostPath` directory fails pod startup — paths must exist first.

### Testing Strategy

There is no unit-test harness (no application code). Validation is **operational**:

- `argo lint <file>.yaml` to check manifest validity before submit
- local dry-runs via `local_run_pipeline_first_time.sh` (Docker Desktop + WSL2, CPU)
- a real submission on the cluster (`argo submit … --watch`) against a reference scan set
- (A4, later) end-to-end on a reference scan: idempotent re-delivery + notification on
  success **and** failure

Because the standard Python/test/build dev-commands don't apply, this repo's
`.claude/commands` suite deliberately **omits** `dev`/`lint`/`test`/`coverage`/`tdd`/
`build`/`pre-merge`/`validate-env`/`run-ci-locally` and keeps the repo-agnostic
git/GitHub/OpenSpec/docs commands.

### Git Workflow

- Branch off `main`; kebab-case, verb-led branch names (`add-*`, `fix-*`, `chore/*`).
- Conventional commit messages.
- One **OpenSpec change → one PR** for any change that adds/alters orchestration behavior
  (per the bloom-integration roadmap's "one OpenSpec PR per change" rule).
- PR → review → squash-merge to `main`.

## Domain Context

- **SLEAP** (`sleap.ai`) is the pose-estimation framework producing the root keypoint
  predictions that traits are computed from.
- This pipeline is part of the **Salk Harnessing Plants Initiative** phenotyping program.
- The broader program is tracked in `docs/bloom-integration/roadmap.md` (canonical for
  scope/sequencing) and Bloom EPIC #9 (canonical for Bloom-side implementation detail).
  This repo owns roadmap tier **A4 — event-driven orchestration**.
- **Vocabulary:** a *scan* is one imaging run of a plant; the pipeline runs per scan (A4),
  while experiment-level `analyze` is a separate, on-request path (not in this repo).

## Important Constraints

- **Argo stays** — orchestration remains declarative YAML (a hard constraint from the
  roadmap); do not replace it with an imperative driver.
- **Warm predict worker + stateless traits jobs** — avoid per-scan model reload (A4 design
  constraint).
- GPU support under the **WSL2 Kubernetes backend is not available** — local testing is
  CPU-only; GPU paths are exercised only on the RunAI cluster.
- `hostPath` volumes with `type: Directory` must already exist on the node or pod startup
  fails.

## External Dependencies

- **RunAI GPU cluster** (`gpu-master:8888` Argo server, `runai-talmo-lab` namespace);
  requires `runai login` + an exported `ARGO_TOKEN`.
- **Stage container images** (GHCR), built/published by sibling repos:
  `models-downloader`, `sleap-roots-predict`, `sleap-roots` (trait-extractor).
- **`argo` CLI** and **`kubectl`** for template creation, submission, and log retrieval.
- (Planned, A4) **Bloom** (local server) as the scan-ingest event source and write-back
  target, via the `sleap-roots-contracts` `ResultEnvelope` contract.
