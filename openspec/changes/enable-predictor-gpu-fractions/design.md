## Context

Full investigation, measured data, and RunAI-docs verification live in
`docs/superpowers/specs/2026-08-04-gpu-fraction-sizing-design.md` (written before this change was
formalized as an OpenSpec proposal). This file summarizes the decisions that matter for
implementation/review; read the linked doc for the full measured-VRAM trace, the busch-lab
quota investigation, and the RunAI-docs verification in detail — it is not duplicated here.

## Goals / Non-Goals

- **Goal**: make the predictor's GPU request actually fractional (it's currently inert — issue
  #25), sized from real measured data, verified against RunAI's actual docs.
- **Non-Goal**: touch any other template, the local-WSL2 dev variant, or the idempotency gap
  (issue #37). Not attempting Dynamic GPU Fractions (request/limit split) — no evidence yet that
  the workload's memory is bursty enough to need it.

## Decisions

- **`gpu-memory: "8192"` (absolute MiB) at `spec.templates[predictor].metadata.annotations`**, not
  a relative `gpu-fraction`. Sized from a measured ~4,676 MiB peak (see linked doc), ~1.75x margin.
- **Remove `resources.limits.nvidia.com/gpu: 1`** — RunAI's own docs example for annotation-driven
  fractional/absolute GPU requests carries no `nvidia.com/gpu` resource at all; coexistence is also
  empirically what caused issue #25 (the annotation was ignored while `nvidia.com/gpu: 1` was
  present).
- **Remove `privileged: true` / `runAsUser: 0`** from `securityContext` — confirmed unnecessary via
  a live run, and independently, cluster admission policy now rejects `privileged` outright.
  **Evidence for the rejection claim** (added per PR #41 review — this was tested live earlier in
  the same investigation but the evidence never made it into this doc): a `runai workspace submit
  --privileged --run-as-uid 0` attempt against `runai-talmo-lab` was rejected outright with
  `Error: failed to submit. The workload request does not comply with the policy set by the
  administrator. Field: security.privileged, Details: the administrator prohibited changing the
  value of this field`. This is a real, observed admission-policy rejection, not an inference —
  though it was only exercised via the `runai workspace submit` CLI path, not a raw `argo submit`;
  see the Open Questions section below for the one place this leaves genuinely unconfirmed
  (`trait-extractor`, submitted via Argo, still has `privileged: true` and has not itself hit this
  rejection in any run so far).
- **Alternatives considered** (full reasoning in the linked doc): relative `gpu-fraction` (rejected
  — absolute sizing is more precise and yields more concurrency across differently-sized cards);
  Dynamic GPU Fractions (rejected — measured trace was a stable plateau, not bursty); a larger,
  lower-concurrency reservation (rejected — defeats the purpose of the change).

## Risks / Trade-offs

- **Annotation-only GPU scheduling is unverifiable by static review** — Kubernetes' standard
  scheduler only considers `nvidia.com/gpu` for node/GPU placement; with that resource removed,
  placement onto a GPU node depends entirely on RunAI's scheduler intercepting the annotation. This
  is real behavior only a live pod can confirm (tasks.md §3) → mitigation: task 3.2 explicitly
  inspects the resulting pod's `annotations`/`resources`/`schedulerName`, not just "the run
  succeeded."
- **NFS cold-path permission risk — exercised, did not materialize.** This repo already documents
  this exact failure class by name for `images-downloader` (`sleap-roots-pipeline.yaml`'s own
  comment): a `DirectoryOrCreate` hostPath gets created root-owned by kubelet, and a non-root
  container can hit permission-denied on a genuinely fresh path. Tasks.md §3.4 tested this directly
  (brand-new, never-before-written output directory) — the write succeeded (mounted `0777` on this
  cluster's actual NFS config).
- **NFS warm-path permission risk — exercised, did not materialize.** §3.4's fresh-directory test
  is not the same scenario as "a non-root process creating new files inside a directory tree that
  already existed, previously populated by the old `runAsUser: 0` predictor." The real, months-old
  `a4_poc/predictions` tree is exactly that case, and the live-DAG run against it (§3.3) had hit
  skip-if-done for every scan, performing zero actual writes there. Tasks.md §3.5 closed this gap:
  forced a real (non-skipped) write into the pre-existing `scan_1009/` directory (created
  2026-07-29, under the old root-owned predictor) by clearing its files first. Result: the
  non-root predictor wrote 4 fresh files successfully, no permission error, confirmed via file
  timestamps. Both permission-risk classes (cold-path and warm-path) are now live-tested, not
  just asserted.
- **Mid-flight template-swap hazard — mechanism corrected per PR #41 review.** Originally described
  here as "a non-root retry may lack permission to *overwrite* a root-owned partial file." That's
  not quite right: the predictor template's own `retryStrategy` comment states skip-if-done is
  **existence-only** — a retry that finds a file already exists (even truncated/corrupt) *skips*
  it rather than attempting to overwrite it, so a permission-denied-on-overwrite failure mode
  doesn't actually apply here. The real risk if a template swap lands mid-retry is the *existing*
  one this repo already tracks separately (predict #26 / sleap-roots #259: existence-only skip +
  non-atomic write can trust a truncated file as "done") — this change doesn't introduce a new
  failure mode, it just means that pre-existing risk's next occurrence could involve a mix of
  root- and non-root-authored files rather than being purely a same-UID question. Low probability
  for a controlled first rollout → documented in tasks.md §6, not blocking, not a new bug.
- **Manual re-registration path has no enforced ordering.** `runai_run_pipeline.sh`'s scripted path
  always re-registers all four templates before submit; the documented manual alternative
  (`argo template update` run by hand) has no such guard — forgetting it silently keeps serving the
  stale template. Documented, not fixed by this change (out of scope: launcher script behavior).

## Migration Plan

Single-file edit, no rename, no mount/param changes. Register the updated template
(`argo template update`) before the next submit on either the scripted or manual path. Rollback:
revert by re-adding the removed fields to the file and re-registering (PR #41 is open; use a
normal revert commit post-merge, not history rewriting) — no cluster-side migration step, no data
format change.

## Open Questions

- Does cluster admission policy's `privileged` rejection apply broadly enough that
  `trait-extractor`'s still-`privileged: true` template is already failing at admission today,
  independent of this change? Not investigated here; if tasks.md §5's full-DAG run fails at the
  `trait-extractor` stage, that's evidence of a pre-existing issue this change's research
  surfaced, not a regression this change caused.
