# Tasks: add-pipeline-concurrency-semaphores

Commit order is chosen so no commit gates a template before something creates its ConfigMap: an
unreferenced ConfigMap is inert. Every commit leaves `bash scripts/check_all.sh` and
`bash scripts/lint_manifests.sh` (WSL) green.

## 1. ConfigMap

- [x] 1.1 Add `sleap-roots-pipeline-semaphores.yaml` (ConfigMap `sleap-roots-pipeline-semaphores`,
  namespace `runai-busch-lab`, label `project: busch-lab`, `pipeline-gpu: "8"`,
  `pipeline-stage-in: "5"`), whose header is the canonical statement of the gate's semantics, deploy
  order and safe retune.
- [x] 1.2 `check_manifests.py`: ConfigMap kind/name/namespace/label; keys exactly the two; values
  quoted `^[1-9][0-9]*$`; `pipeline-gpu` ≤ 10. Validate: `check_all.sh` green; mutation harness
  (tasks 3.3, 2.3) fails on `"11"`, `"0"`, unquoted `8`, an extra key, a deleted key and a wrong
  namespace.

## 2. Launcher

- [x] 2.1 `runai_run_pipeline.sh`, before the template loop: abort without `kubectl`; print the
  `kubectl` context; `kubectl get configmap … --ignore-not-found -o name` (abort if it fails);
  create only if empty; otherwise validate each key and abort if missing or non-integer. Never
  update. Update the header's manual steps and the runtime NOTE lines.
- [x] 2.2 `check_manifests.py`: exactly one `kubectl create`, of the ConfigMap file, on the
  empty-result branch, before the loop; abort branches end in `exit 1` within their own `if`; no
  `kubectl apply|replace|edit|patch`; the launcher's validated key list equals the ConfigMap's keys.
- [x] 2.3 Validate behaviour with stubbed `kubectl`/`argo` on a `/c/...` PATH (Git Bash), asserting
  `command -v kubectl` is the stub and logging every call: `get` fails → exit 1, no `argo` call;
  `get` empty → `kubectl create` logged before the first `argo`; exists with valid keys → no create;
  exists with a key missing → exit 1, no `argo` call. Plus launcher mutations (create moved after the
  loop; `apply` instead of `create`; abort branch without `exit`) each fail `check_manifests.py`.

## 3. Templates

- [x] 3.1 Gate `predictor` on `pipeline-gpu` and `images-downloader` on `pipeline-stage-in`
  (`synchronization.semaphores[].configMapKeyRef`), each with a short comment pointing to the
  ConfigMap file.
- [x] 3.2 `check_manifests.py`: each template holds exactly its own ref, and no other
  `synchronization` field; predictor `gpu-memory` is `"8192"`.
- [x] 3.3 Validate: `check_all.sh` green; `lint_manifests.sh` (WSL) clean with "Linting 6
  manifests"; mutations fail (wrong key; singular `semaphore:`; `gpu-memory: "12288"`).

## 4. Drift check

- [x] 4.1 `check_cluster_drift.sh`: compare the live ConfigMap's `data` (`--ignore-not-found -o
  yaml`: non-zero → CHECK FAILED 2; empty → NOT CREATED; differs → DRIFT with repo/live values);
  change the template loop's `drift=1` to `[ "$drift" -eq 0 ] && drift=1`.
- [x] 4.2 Validate with a stubbed `kubectl` (Git Bash; `python3` stubbed to `python`): in sync → 0;
  retuned → DRIFT, 1; missing → NOT CREATED, 1; `get` fails → CHECK FAILED, 2; an earlier CHECK
  FAILED plus a later DRIFT → still 2. Then read-only live (WSL): the gated templates show DRIFT and
  the ConfigMap NOT CREATED, exit 1 — record as the pre-deploy baseline.

## 5. Docs

- [x] 5.1 `README.md`: prerequisites (`kubectl` + `KUBECONFIG`), the folder tree, "This script
  will", and the manual Kubernetes-mode steps (create the ConfigMap first).
- [x] 5.2 `docs/cluster-identities.md`: what the gate bounds (the pipeline's non-preemptible GPU
  use), and a pointer to the ConfigMap header for values and the validated retune.
- [x] 5.3 `.claude/commands/ci-debug.md` and `.claude/skills/runai/SKILL.md` §8: "Waiting for …
  lock" (expected; retune) and "Error: … not found in ConfigMap" (deploy order / deleted ConfigMap).
- [x] 5.4 A4 design §9: annotate what was built (tasks, not batches; two keys; write-back not gated;
  busch-lab, not talmo-lab).
- [x] 5.5 `openspec/project.md`: fix the Purpose sentence's whole open-work list (the semaphore and
  the Bloom dispatch worker are built), the Domain Context's equivalent claim, the
  `NonPreemptibleOverQuota` advice (don't move the predictor to `interactive-preemptible`), and the
  launcher's prerequisites.
- [x] 5.6 Validate: `python scripts/check_docs.py` green; `grep -n "semaphore" openspec/project.md`
  shows no open-work claim.

## 6. Pre-PR sweep

- [x] 6.1 `bash scripts/check_all.sh` → `=== OK: all suites pass ===`; `lint_manifests.sh` (WSL)
  clean; `openspec validate add-pipeline-concurrency-semaphores --strict` → "is valid". The offline
  checks prove shape and wiring only; scheduling and lock claims rest on section 7.

## 7. Deploy and live verification — after merge, each step needs the owner's go-ahead

- [ ] 7.0 (Required before 7.3) Semantics test in `runai-talmo-lab`, not busch-lab: a test ConfigMap at limit
  1, a sleep template with retries and the semaphore, three `busybox` Workflows. Confirms: Pending
  with no pod and the message format; FIFO; lazy raise; release on `kubectl delete wf`; Error on a
  deleted ConfigMap; and that the controller can read ConfigMaps. Include one gated template with a
  `retryStrategy` whose first attempt fails (`exit 1` when `{{retries}}` is `0`) and that must wait
  for a slot first: assert its node type is `Retry`, a child `(1)` runs after the backoff, and the
  slot stays held meanwhile. First confirm its pods run `argoexec:v3.6.7` and
  `kubectl auth can-i create workflows,configmaps`.
- [ ] 7.1 `check_cluster_drift.sh` → record as the rollback pre-image.
- [ ] 7.2 `argo list -n runai-busch-lab` → no `sleap-roots-pipeline-*` Workflow Running or Pending.
- [ ] 7.3 `kubectl create -f sleap-roots-pipeline-semaphores.yaml`, then `argo template update` the
  images-downloader and predictor templates, from `main` at the squash commit. Immediately submit
  one small manual run and `argo get` it: if a gated node shows a ConfigMap error (the controller
  cannot read it), roll back at once per design.md's Migration Plan — Bloom batches dispatched in
  the meantime would Error the same way.
- [ ] 7.4 `check_cluster_drift.sh` → exit 0, `IN SYNC sleap-roots-pipeline-semaphores`.
- [ ] 7.5 Lock test, two phases, using already-processed scan IDs so write-back is idempotent;
  re-check the namespace is idle immediately before each retune (it throttles prod and staging too).
  Submit with `argo submit sleap-roots-pipeline.yaml --parameter scan-ids=<ids> --labels
  purpose=srp98-lock-test -n runai-busch-lab` (manual runs carry no `environment` label: refer to
  them by name or this label). Phase A, `pipeline-stage-in: "2"`, `pipeline-gpu: "1"`: two runs;
  the second's predictor is Pending with the `pipeline-gpu` lock message and has no pod
  (`kubectl get wf <wf2> -o jsonpath='{.status.nodes[*].message}'`;
  `kubectl get pods -l workflows.argoproj.io/workflow=<wf2>`). Phase B, `pipeline-stage-in: "1"`:
  the same for the downloader. Every run ends `Succeeded`, and a task that waited then acquired still
  retries and feeds its exit code to the gate. An inconclusive phase is a failure, not a pass.
- [ ] 7.6 Restore `pipeline-gpu: "8"` and `pipeline-stage-in: "5"` in the same session;
  `check_cluster_drift.sh` → exit 0.

## 8. After merge

- [ ] 8.1 Draft the roadmap update for the owner's approval: A4 row (line ~138, "the
  RunAI-quota/semaphore layer (§9)"), the workflow-template row (line ~303, "semaphore … remain
  unbuilt"), Sequencing, a dated status-log entry, and the close-the-loop checklist (#98 and epic
  #10). Acceptance: draft shown to the owner; nothing posted without approval.
- [ ] 8.2–8.5 Draft (do not file) follow-up issues; acceptance: each draft shown to the owner.
  - 8.2 bloomctl: a deterministic 404 on stage-in is indistinguishable from a transient failure, so
    the downloader's retries spend attempts on it.
  - 8.3 Bloom: a Workflow waiting on a semaphore is `Running` in Argo (its step is `Pending`), so
    the run panel shows a queued batch as a slow one; surface the lock wait.
  - 8.4 Record whether the workflow-controller's service account can `get` ConfigMaps in
    `runai-busch-lab` (from 7.0 or 7.5) in `docs/cluster-identities.md`.
  - 8.5 Remove the unmaintained `local-WSL2-*` manifests and `local_run_pipeline_first_time.sh`
    (see #21), with the `project.md` and README references to them.
- [ ] 8.6 Draft (do not file) a follow-up: a pending-pod timeout for the gated templates, so a pod
  that never schedules (hostPath mount failure, ImagePullBackOff, `NonPreemptibleOverQuota`) stops
  holding a slot; first check whether Argo applies `activeDeadlineSeconds` to an unscheduled pod.
  Acceptance: draft shown to the owner.
- [ ] 8.7 Archive the change (`/cleanup-merged`) in the same post-merge PR that ticks section 7,
  repointing links to `openspec/changes/add-pipeline-concurrency-semaphores/` at the archive path.
