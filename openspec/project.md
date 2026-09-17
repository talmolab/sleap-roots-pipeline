# Project Context

## Purpose

`sleap-roots-pipeline` is the **orchestration layer** for the sleap-roots plant-root
phenotyping pipeline. It declares how four containerized stages — plus a terminal exit-code gate
— are wired together and scheduled on a GPU cluster:

1. **images-downloader** — stages a batch of scans in from Bloom via `bloomctl` (batch-capable, A4)
2. **predictor** — runs SLEAP predictions on the staged image sets (GPU)
3. **trait-extractor** — extracts phenotypic traits from the predictions
4. **write-back** — writes the resulting traits back into Bloom via `bloomctl` (batch-capable, A4)

This repo holds **no application/library code of its own** — it is the declarative glue
(Argo `Workflow` + `WorkflowTemplate` manifests and shell launchers) that runs images
built and published by the sibling service repos (`sleap-roots-predict`, `sleap-roots`
trait-extractor, `salk-bloom`'s `bloomctl`).

The roadmap target (see `docs/bloom-integration/roadmap.md`, tier **A4**) is
**event-driven, per-batch orchestration**: a scan ingested into Bloom eventually triggers
this per-batch Argo workflow (stage-in → predict → traits → write-back with provenance).
**A4 is in progress, not out of scope** — the batch DAG above landed via
`add-per-batch-argo-workflow` and was validated end-to-end on the real RunAI cluster
(2026-07-30). Still open: the Bloom-side trigger route/dispatch worker (so a UI click
submits this workflow instead of a manual `argo submit`), the Argo semaphore for
concurrent-batch concurrency, and per-run path isolation — see the roadmap's A4
change-breakdown table for the full remaining list.

## Tech Stack

- **Argo Workflows** — DAG orchestration (`sleap-roots-pipeline.yaml` entrypoint +
  `*-template.yaml` `WorkflowTemplate`s referenced via `templateRef`)
- **Argo Events** — (planned, A4) scan-ingest → workflow trigger
- **RunAI** — GPU scheduling on the `runai-busch-lab` namespace (fractional GPU via a pod-level
  `gpu-memory` annotation — absolute MiB, not the relative `gpu-fraction` annotation, which must
  also live at `spec.templates[].metadata.annotations`, not the WorkflowTemplate object's own
  metadata, or Argo never copies it to the pod — see issue #25; `preemptible`, `project` labels
  for quota)
- **Kubernetes** — execution substrate; `hostPath` volumes (cluster: NFS-backed
  `/hpi/hpi_dev/...`) for model/image/output mounts; `nvidia.com/gpu` resource limits
- **Bash** — launchers (`runai_run_pipeline.sh` for the cluster,
  `local_run_pipeline_first_time.sh` for local Docker Desktop + WSL2 testing)
- **Docker** — stage images are built in their own repos and *consumed* here. Every cluster
  template pulls from **GHCR**: `ghcr.io/talmolab/{sleap-roots-predict, sleap-roots-trait-extractor}`
  for the two producers, and `ghcr.io/salk-harnessing-plants-initiative/bloomctl` for the
  `images-downloader`, `write-back` and `exit-gate` stages. The GitLab registry
  (`registry.gitlab.com/salk-tm/...`) survives only in the three stale `local-WSL2-*` templates,
  which also still reference a `models-downloader` stage the cluster DAG no longer has (#21)

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
- **Pin images by tag/digest**, never `:latest`. The two producer templates
  (`predictor`, `trait-extractor`) MUST be pinned by `@sha256:` digest, because each injects a
  digest env var validated against that line; the `bloomctl` stages remain tag-pinned (the exit-gate's pin is tracked as #72; images-downloader
  and write-back are untracked).
- Shell scripts should be safe (`set -euo pipefail`) and must never echo `ARGO_TOKEN` or
  other secrets.

### Architecture Patterns

- **Per-batch DAG with a terminal exit-code gate**: images-downloader → predictor →
  trait-extractor → write-back → exit-gate, with `dependencies:` enforcing order and
  `retryStrategy` handling preemption/transient failures. The three producers carry
  `continueOn: {failed: true}` so a partial batch does not kill the run, and `exit-gate` — the
  DAG's only leaf — re-derives the Workflow phase from their real exit codes (`0`/`3` pass,
  anything else fails). See `openspec/changes/add-partial-success-exit-gate/`.
  Data passes between stages **via shared volume mounts,
  not Argo parameters/artifacts** — one stage's output mount is the next stage's input
  mount, so inter-stage coupling is mount-path agreement, not parameter wiring. (The one
  exception is the `scan-ids` Workflow parameter, which `images-downloader` consumes to
  know which batch to stage.)
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

- `bash scripts/lint_manifests.sh` (from WSL, where `argo` lives) — lints the Workflow **together
  with every template it references**, in one invocation. Use the script, **not** the bare command:
  `argo lint --offline sleap-roots-pipeline.yaml sleap-roots-*-template.yaml` **fails on this tree**
  even though the tree is valid. Offline lint does resolve `templateRef` from the files you pass,
  but it matches on **(namespace, name)**, and `sleap-roots-pipeline.yaml` declares
  `metadata.namespace` while the templates declare none — so the lookup always misses. The script
  lints a temp copy with that one line stripped and never touches the tracked files. Never strip it
  from the real file. What this catches is a `templateRef` with **no matching file in this repo**;
  it says nothing about what is *registered in the cluster* — that is
  `scripts/check_cluster_drift.sh`'s job (it reports `NOT REGISTERED`), and it matters because a
  template must be `argo template create`d before any Workflow referencing it can be submitted.
- `python scripts/check_manifests.py` — executable assertions for this repo's own conventions,
  which `argo lint` knows nothing about (priority classes, quota labels, credential isolation,
  retry shape, pin hygiene, mount agreement). Includes the exit-gate's allowlist, asserted by
  **executing** the shipped script over a vector table rather than inspecting its text.
- field assertions on the manifests (`yq`) for anything `argo lint` does not check — it validates
  Argo schema, not whether a pod carries a `priorityClassName`, a quota label, or a `retryStrategy`
- local dry-runs via `local_run_pipeline_first_time.sh` (Docker Desktop + WSL2, CPU). ⚠️ Currently
  broken for the A4 DAG, and for two reasons in this order: it applies its four templates into
  namespace `argo` but submits the *cluster* manifest, whose `metadata.namespace`
  (`runai-busch-lab`) wins over `--namespace` — so it fails on the missing namespace first; and if
  it got past that, **all** of its `templateRef`s would be unresolvable (the templates are in
  `argo`), not only the new `exit-gate`. Tracked by #21.
- a real submission on the cluster (`argo submit … --watch`) against a reference scan set —
  including the **failure** paths, not just the happy one: a partial batch should end `Succeeded`
  with the good scans written back, and a crash-class exit should end `Failed`
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
  event-driven orchestration**; A4 is **in progress** — the batch DAG is built
  and cluster-validated, but the Bloom-side trigger route (so a UI click submits it,
  rather than a manual `argo submit`) is not yet built.
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

- **RunAI GPU cluster** (`gpu-master:8888` Argo server, `runai-busch-lab` namespace);
  requires `runai login` + an exported `ARGO_TOKEN`.
- **Stage container images**, all on GHCR: `sleap-roots-predict` and `sleap-roots` (which
  publishes `sleap-roots-trait-extractor`) under `ghcr.io/talmolab`, and `bloomctl` under
  `ghcr.io/salk-harnessing-plants-initiative`.
- **`argo` CLI** and **`kubectl`** for template creation, submission, and log retrieval.
- (Planned, A4) **Bloom** (local server) as the scan-ingest event source and write-back
  target, via the `sleap-roots-contracts` `ResultEnvelope` contract.
