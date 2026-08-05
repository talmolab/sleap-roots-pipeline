## Why

`sleap-roots-predictor-template.yaml` declares `gpu-fraction: "0.5"` at the WorkflowTemplate
object's `metadata.annotations`, but Argo never copies object-level annotations onto the pod — the
container's `resources.limits.nvidia.com/gpu: 1` is what actually takes effect, so every predictor
pod claims a whole GPU regardless. Tracked as
[issue #25](https://github.com/talmolab/sleap-roots-pipeline/issues/25). This blocks useful
concurrency on small GPU quotas — specifically `runai-busch-lab`, whose real configured quota is 2
GPUs. Full investigation, measured VRAM data, and RunAI-docs verification: `design.md` (this
folder) and `docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md`.

## What Changes

- Move `gpu-memory: "8192"` (absolute MiB, not a relative `gpu-fraction`) to
  `spec.templates[predictor].metadata.annotations` (pod-level), so Argo actually places it on the
  pod. Sized from a measured ~4,676 MiB peak — see `design.md` for the full sizing rationale and
  RunAI-docs verification.
- Remove `resources.limits.nvidia.com/gpu: 1` from the predictor container — fractional/absolute
  GPU-memory requests and whole-GPU limits are mutually exclusive in RunAI's model.
- Remove `privileged: true` and `runAsUser: 0` from the predictor's `securityContext` — confirmed
  unnecessary via a live test run, though see `design.md`'s Risks section: that test reused an
  already-writable shared path, not a fresh one, so the cold-path permission risk this repo
  already documents for `images-downloader` isn't yet exercised for predictor either. This
  proposal adds that test (tasks.md §3).
- Confirm `schedulerName: runai-scheduler` lands on the resulting pod (expected automatic in
  `runai-talmo-lab`/`runai-busch-lab`).

**BREAKING**: expected none, but not yet fully proven — see `design.md`'s first Risk.
`predictor`'s inputs/outputs/image/args are unchanged, and the workload never used more than ~10%
of the GPU it previously claimed, so a regression is unlikely. However, annotation-only GPU
scheduling (no `nvidia.com/gpu` resource at all) is not verifiable by static review — it depends
on RunAI's scheduler intercepting the annotation, which only a live pod (tasks.md §3.2) can
confirm. Treat this as "expected non-breaking, confirmed by task 3" rather than a settled fact
until that task runs.

## Impact

- **Modified capability:** `per-batch-pipeline` — the "Predictor runs the warm GHCR predict
  container" requirement's scenario currently asserts the predictor "requests `nvidia.com/gpu`";
  this changes to asserting the pod-level `gpu-memory` annotation with no `nvidia.com/gpu` limit
  and no `privileged`/`runAsUser: 0`.
- **Affected code:** `sleap-roots-predictor-template.yaml` only.
- **Affected docs:** `README.md` (its "Run:AI-Specific Configuration" and "GPU Support" sections
  describe the current `gpu-fraction`/`nvidia.com/gpu` shape, already inaccurate today per issue
  #25 and would become actively backwards if left unfixed), `.claude/skills/runai/SKILL.md`
  (references `gpu-fraction`/`--gpu-portion-request` in its operational flag table and worked
  example), `openspec/project.md` (Tech Stack line names `gpu-fraction` as the mechanism),
  `docs/bloom-integration/roadmap.md` (needs a closing status-log entry — issue #25 is referenced
  twice there already as filed/open). See tasks.md §7.
- **Untouched code:** `sleap-roots-trait-extractor-template.yaml`,
  `sleap-roots-images-downloader-template.yaml`, `sleap-roots-write-back-template.yaml`,
  `sleap-roots-pipeline.yaml`, `runai_run_pipeline.sh`, all `local-WSL2-*` files.
- **External prerequisites:** none — this is entirely self-contained pipeline-side engineering,
  no cluster-admin action needed.
