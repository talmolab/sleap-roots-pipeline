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
  unnecessary via two live tests (tasks.md §3.4, §3.5): a non-root write against a brand-new
  `DirectoryOrCreate` path, and against a pre-existing directory tree originally populated by the
  old root-owned predictor. Both passed — the cold-path permission risk this repo documents for
  `images-downloader` does not materialize for predictor on this cluster's actual NFS config.
- Explicitly set `spec.templates[predictor].schedulerName: runai-scheduler` (added per PR #41
  review) — live-verified as automatic in `runai-talmo-lab` already, set explicitly anyway as
  defense-in-depth against future cluster/namespace config drift, since the annotation-only GPU
  request has no `nvidia.com/gpu` fallback if that wiring ever changes.

**BREAKING**: none, live-cluster confirmed. `predictor`'s inputs/outputs/image/args are unchanged,
and the workload never used more than ~10% of the GPU it previously claimed. Annotation-only GPU
scheduling (no `nvidia.com/gpu` resource at all) isn't verifiable by static review alone, but
tasks.md §3.2 confirms it on a real pod (`gpu-memory`/`schedulerName`/resources all correct), §3.4
and §3.5 confirm both permission-risk classes, and §4 confirms real concurrent co-scheduling.

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
  `sleap-roots-pipeline.yaml`, `runai_run_pipeline.sh`. `local-WSL2-sleap-roots-predictor-template.yaml`
  is functionally untouched (still `nvidia.com/gpu: 1`, still `privileged`/`runAsUser: 0`) — one
  comment added (per PR #41 review) flagging that it now diverges from the cluster template on
  the root/non-root question and can no longer stand in for that specific test.
- **External prerequisites:** none — this is entirely self-contained pipeline-side engineering,
  no cluster-admin action needed.
