## Why

`sleap-roots-predictor-template.yaml` declares `gpu-fraction: "0.5"` at the WorkflowTemplate
object's `metadata.annotations`, but Argo never copies object-level annotations onto the pod — the
container's `resources.limits.nvidia.com/gpu: 1` is what actually takes effect, so every predictor
pod claims a whole GPU regardless of the annotation. Tracked as
[issue #25](https://github.com/talmolab/sleap-roots-pipeline/issues/25), which already contains a
live-pod repro (no `gpu-fraction` in the pod's annotations, `runai-total-requested-gpus: "1"`).

This blocks useful concurrency on small GPU quotas — specifically `runai-busch-lab`, whose real
configured quota is 2 GPUs (confirmed via `runai project list`, not assumed).

Grounded in the approved design:
`docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md`, which includes a real measured
VRAM trace (not a guess) from a live warm-batch predictor run on the actual production image.

Deliberately **deferred**: Dynamic GPU Fractions (request/limit split) — the measured trace was a
stable plateau, not bursty, so the added complexity isn't earned yet; revisit if a real
large-batch production run shows memory growth this change's 3-scan test didn't. Also deferred:
any change to `trait-extractor`, `images-downloader`, `write-back`, or the
`local-WSL2-sleap-roots-predictor-template.yaml` dev variant (GPU fractions have no local-dev
equivalent), and the idempotency/skip-if-done gap (issue #37, separate in-progress work).

## What Changes

- Move `gpu-memory: "8192"` (absolute MiB, not a relative `gpu-fraction`) to
  `spec.templates[predictor].metadata.annotations` (pod-level), so Argo actually places it on the
  pod. Verified directly against RunAI's own docs (not just issue #25's description of them):
  annotations are pod-level, `schedulerName: runai-scheduler` is required, and RunAI supports both
  a relative `gpu-fraction` and an absolute `gpu-memory` annotation — the docs recommend the
  absolute form for precision. Sized from the design doc's measured peak (~4,676 MiB), giving
  ~1.75x headroom over the 3-scan test batch and allowing ~5 predictor pods to co-schedule per
  physical GPU (more than the flat-percentage approach originally planned, since a fixed fraction
  wastes headroom differently on talmo-lab's ~46GB card vs. busch-lab's ~48GB card).
- Remove `resources.limits.nvidia.com/gpu: 1` from the predictor container — fractional and
  whole-GPU limits are mutually exclusive in RunAI's model.
- Remove `privileged: true` and `runAsUser: 0` from the predictor's `securityContext` — confirmed
  unnecessary via a live test run (GPU visible via device-plugin without `privileged`; NFS writes
  to the hostPath output succeeded as the default non-root user). Independently, cluster admission
  policy now rejects `security.privileged` on `runai workspace submit` outright.
- Confirm `schedulerName: runai-scheduler` lands on the resulting pod (expected automatic in
  `runai-talmo-lab`/`runai-busch-lab`).

**BREAKING**: none. `predictor`'s inputs/outputs/image/args are unchanged; only its GPU-scheduling
and security-context shape changes. A pod that previously got a whole GPU now gets a 0.25 fraction
— existing single-pod runs are unaffected in practice (the workload never used more than ~10% of
the GPU it was allocated).

## Impact

- **Modified capability:** `per-batch-pipeline` — the "Predictor runs the warm GHCR predict
  container" requirement's scenario currently asserts the predictor "requests `nvidia.com/gpu`";
  this changes to asserting the pod-level `gpu-memory` annotation with no `nvidia.com/gpu` limit
  and no `privileged`/`runAsUser: 0`.
- **Affected code:** `sleap-roots-predictor-template.yaml` only.
- **Untouched:** `sleap-roots-trait-extractor-template.yaml`,
  `sleap-roots-images-downloader-template.yaml`, `sleap-roots-write-back-template.yaml`,
  `sleap-roots-pipeline.yaml`, `runai_run_pipeline.sh`, all `local-WSL2-*` files.
- **External prerequisites:** none — this is entirely self-contained pipeline-side engineering,
  no cluster-admin action needed.
