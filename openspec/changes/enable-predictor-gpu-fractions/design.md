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
- **NFS cold-path permission risk, not yet exercised.** This repo already documents this exact
  failure class by name for `images-downloader` (`sleap-roots-pipeline.yaml`'s own comment): a
  `DirectoryOrCreate` hostPath gets created root-owned by kubelet, and a non-root container can hit
  permission-denied on a genuinely fresh path. The live test that "confirmed" dropping
  `privileged`/`runAsUser: 0` is safe reused the already-writable shared `a4_poc` output path, not
  a fresh one — so this risk class remains unverified for the predictor too → mitigation: tasks.md
  §3 adds an explicit fresh-path test.
- **Mid-flight template-swap hazard.** If a Workflow is retrying (per `retryStrategy limit: 3`)
  when the template is updated on the cluster, a retry could resolve to the new non-root template
  while a root-owned partial file from a prior (old-template) attempt still sits in the shared
  output path — a non-root process may lack permission to overwrite it. Low probability for a
  controlled first rollout, not eliminated → documented in tasks.md §6, not blocking.
- **Manual re-registration path has no enforced ordering.** `runai_run_pipeline.sh`'s scripted path
  always re-registers all four templates before submit; the documented manual alternative
  (`argo template update` run by hand) has no such guard — forgetting it silently keeps serving the
  stale template. Documented, not fixed by this change (out of scope: launcher script behavior).

## Migration Plan

Single-file edit, no rename, no mount/param changes. Register the updated template
(`argo template update`) before the next submit on either the scripted or manual path. Rollback:
since the branch is unpushed pre-PR, revert by re-adding the removed fields to the file (or `git
revert`/amend post-PR) — no cluster-side migration step, no data format change.

## Open Questions

- Does cluster admission policy's `privileged` rejection apply broadly enough that
  `trait-extractor`'s still-`privileged: true` template is already failing at admission today,
  independent of this change? Not investigated here; if tasks.md §5's full-DAG run fails at the
  `trait-extractor` stage, that's evidence of a pre-existing issue this change's research
  surfaced, not a regression this change caused.
