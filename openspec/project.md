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
- **Kubernetes** — execution substrate; `hostPath` volumes (cluster: NFS-backed
  `/hpi/hpi_dev/...`) for model/image/output mounts; `nvidia.com/gpu` resource limits
- **Bash** — launchers (`runai_run_pipeline.sh` for the cluster,
  `local_run_pipeline_first_time.sh` for local Docker Desktop + WSL2 testing)
- **Docker** — stage images are built in their own repos and *consumed* here. They currently
  publish to **GitLab** (`registry.gitlab.com/salk-tm/{models-downloader, sleap-roots-predict,
  sleap-roots-traits}`); migration to **GHCR** is the roadmap A0 target (not yet done)

No Python package, no Node package, no build step, and (currently) no CI — the artifacts
are YAML manifests and shell scripts.

## Project Conventions

### Code Style

- **Declarative YAML first.** Orchestration logic lives in Argo manifests, not imperative
  scripts. Keep `WorkflowTemplate`s small, named, and reusable; the top-level `Workflow`
  wires them with `templateRef` + `dependencies`.
- **Cluster vs. local parity.** Cluster manifests are the canonical set; the
  `local-WSL2-*.yaml` / `local-*.yaml` variants are **Docker-Desktop/WSL2 counterparts, not
  byte-mirrors** — they deliberately differ in template names (`predictor` vs
  `sleap-roots-predictor`) and `retryStrategy` limits. Reconcile **mount/path parity**, not
  template names. (Note: the local-WSL2 predictor template still pins `nvidia.com/gpu: 1`
  despite WSL2 GPU being unavailable — a known stale spot, not a parity rule.) When you change
  one, check the other for *path* drift.
- **Pin images by tag/digest**, never `:latest` — this is the **target** convention for
  reproducibility (full provenance/idempotency is A4, not yet implemented).
- Shell scripts should be safe (`set -euo pipefail`) and must never echo `ARGO_TOKEN` or
  other secrets.

### Architecture Patterns

- **Three-stage DAG**: models-downloader → predictor → trait-extractor, with
  `dependencies:` enforcing order and `retryStrategy` handling preemption/transient
  failures. Data passes between stages **via shared volume mounts, not Argo
  parameters/artifacts** — one stage's output mount is the next stage's input mount, so
  inter-stage coupling is mount-path agreement, not parameter wiring.
- **Templates are versioned, shared building blocks** (`argo template create …`), referenced
  by the workflow rather than inlined.
- **Storage is mount-based**: model input, image input, and outputs are passed between
  stages via `hostPath type: Directory` volumes on **both** cluster and local — the cluster
  mounts the NFS-backed `/hpi/hpi_dev/...` tree, local-WSL2 mounts `/run/desktop/mnt/host/wsl/...`.
  A missing `hostPath` directory fails pod startup — paths must exist first. (PV/PVC appears
  only in the `local-workflow-test.yaml` smoke test, not the production pipeline.)
- **Preemptibility is set by `priorityClassName`, not the `preemptible: "true"` annotation**
  the templates carry (that annotation is a UI/convention breadcrumb only). Run:ai treats
  `priorityClassName` ≥ 100 as non-preemptible and < 100 as preemptible; the lab's
  preemptible GPU class is `interactive-preemptible`. The predictor's GPU jobs typically run
  *within* quota, so over-quota preemption isn't usually exercised — but if a GPU pod is
  blocked at quota (`NonPreemptibleOverQuota`), set
  `priorityClassName: interactive-preemptible` to go over quota.

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
  This repo is the orchestration component slated to **deliver** roadmap tier **A4 —
  event-driven orchestration**; it is currently at **A0** (this change) and A4 is not started.
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
- **Stage container images** (currently `registry.gitlab.com/salk-tm/...`; GHCR is the A0
  target), built/published by sibling repos: `models-downloader`, `sleap-roots-predict`,
  `sleap-roots-traits` (trait-extractor).
- **`argo` CLI** and **`kubectl`** for template creation, submission, and log retrieval.
- (Planned, A4) **Bloom** (local server) as the scan-ingest event source and write-back
  target, via the `sleap-roots-contracts` `ResultEnvelope` contract.
