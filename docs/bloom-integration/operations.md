# Operating the cyl pipeline in production

This page is for whoever changes, rolls back or debugs the pipeline now that Bloom production
dispatches through it (live since 2026-10-04). It owns one procedure, the guard in the first
section. For everything else it gives the rule in a sentence or two and links the source that owns
the detail. Follow the link rather than a copy: the sources are kept current, and this page
deliberately holds no image tags, digests or commit SHAs.

Commands run in WSL with the `argo-user` kubeconfig unless a step says otherwise. The invocation
pattern is in [the runai skill, §1](../../.claude/skills/runai/SKILL.md).

## Before any change to the cluster

Bloom staging and prod run on the same `sleap-roots-*` WorkflowTemplates, the same semaphore
ConfigMap and the same model registry (see
[Cluster identities → Namespace facts that bite](../cluster-identities.md#namespace-facts-that-bite)).
So the following each reach **both** environments at once:

- every `argo template update`, whether a deploy or a rollback;
- `runai_run_pipeline.sh`, which updates all five templates from whatever branch is checked out;
- every registry `production` link or unlink.

Retuning the semaphore limits is separate; its procedure is in the
[ConfigMap header](../../sleap-roots-pipeline-semaphores.yaml).

The guard:

1. **Work from `main`.** Never register a template from an unmerged branch. Run
   `runai_run_pipeline.sh` only from an up-to-date `main`, and only after this guard.
2. **Confirm nothing is in flight.** Prod users can dispatch at any time, so the check has to fail
   closed and has to read each Workflow's `.status.phase`. Count a Workflow with no phase as in
   flight. Don't line-count `argo list -o name`: it prints `No workflows found` when there are
   none, which once aborted a deploy on a false positive (roadmap status log, 2026-10-02
   (deploy)).

   ```bash
   rows=$(kubectl get workflows -n runai-busch-lab \
     -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.phase}{"\n"}{end}') \
     || { echo "could not list workflows: NOT checked" >&2; exit 1; }
   busy=$(printf '%s\n' "$rows" | awk -F'\t' \
     '$1 ~ /^sleap-roots-/ && ($2=="" || $2=="Running" || $2=="Pending")')
   [ -z "$busy" ] || { printf 'in flight:\n%s\n' "$busy" >&2; exit 1; }
   ```

3. **Save a rollback copy** of each template you will change:
   `kubectl get workflowtemplate <name> -n runai-busch-lab -o yaml > <name>.pre.yaml`.
4. **Run the drift check:** `wsl -e bash scripts/check_cluster_drift.sh`. Expect `DRIFT` only on the
   templates you are about to change, and only in the fields you mean to change. A `NOT
   REGISTERED` can also mean a failed read
   ([#109](https://github.com/talmolab/sleap-roots-pipeline/issues/109)).
5. **Apply, in the order the template comments give.** Some pairs must not be applied in the
   wrong order (for example, write-back before images-downloader on a bloomctl bump that changes
   the manifest writer). Re-run step 2 in the same command, immediately before
   `argo template update`.
6. **Read back what is live.** For each changed template, compare the live `image:` with the repo.
   On the predictor or trait-extractor, also compare the digest env var
   (`SRP_PREDICT_CONTAINER_DIGEST` or `SRT_TRAITS_CONTAINER_DIGEST`); it must move with the tag
   and digest.
7. **Run the drift check again.** Expect `IN SYNC` for every template and the ConfigMap. The
   comparison uses parsed YAML, so a comment-only change never drifts and needs no deploy.
8. **Re-check step 2.** The idle check holds only for the moment it ran. If a run started during
   the change, note which images it ran.

A registry `production` link or unlink takes steps 1, 2 and 8. Its procedure lives with the
training repo's issue for that link, for example
[training#72](https://github.com/talmolab/sleap-roots-training/issues/72).

## Switching production off is not a pause

Turning prod's `CYL_PIPELINE_TRIGGER_ENABLED` off is a rollback, not a pause. Bloom's dispatch
worker then fails every batch it claims. The worker reads the switch only at startup, so a change
takes a container restart. See
[Cluster identities → Namespace facts that bite](../cluster-identities.md#namespace-facts-that-bite).
To stop new work reaching the templates without failing users' batches, there is no switch today.
Run the guard and choose a quiet moment instead.

## Rollback

1. **Re-derive the live pins first.** The drift check prints them under "Live image pins". A
   rollback target recorded anywhere may be stale.
2. **Start at the trait-extractor template's `Rollback` comment**
   ([`sleap-roots-trait-extractor-template.yaml`](../../sleap-roots-trait-extractor-template.yaml)).
   It gives the steps in order:
   - wheat and sorghum are linked to `production`, so unlink them first, before re-pinning
     traits; `unlink()` also drops `candidate`;
   - undoing the latest traits deploy re-pins traits alone;
   - going further back (bloom#971 phase 1) moves predict first, as the
     [`sleap-roots-predictor-template.yaml`](../../sleap-roots-predictor-template.yaml) comment
     says.

   Re-pin the tag, the digest and the digest env var together.
3. **bloomctl:** all three bloomctl templates move together, to the target in the
   [`sleap-roots-images-downloader-template.yaml`](../../sleap-roots-images-downloader-template.yaml)
   header, in the order it gives.
4. **Never below the a9 floor.** A pre-a9 bloomctl image would write a legacy `run_manifest.json`
   into both environments' trees. See the roadmap's "Step 7 … is hardening"
   ([roadmap](roadmap.md)).
5. **Every rollback is a change to the cluster.** Run the guard.

## Preconditions nothing enforces

- **Each environment's Secret and three stage directories must exist.** A missing one leaves pods
  `Pending`, not `Failed`, so the run hangs instead of erroring. The paths, Secret names and
  how to create them are in
  [Cluster identities → Getting access](../cluster-identities.md#getting-access-new-bloom-side-developer)
  and [Namespace facts that bite](../cluster-identities.md#namespace-facts-that-bite). The
  directories sit under a personal path with nothing to recreate them
  ([#63](https://github.com/talmolab/sleap-roots-pipeline/issues/63)).
- **A Pending gated pod holds a shared semaphore slot.** Staging, prod and manual runs share one
  pool, so a stuck pod in one environment can starve the other. That holds until a pending-pod
  timeout lands ([#106](https://github.com/talmolab/sleap-roots-pipeline/issues/106)). The
  semaphore [ConfigMap header](../../sleap-roots-pipeline-semaphores.yaml) owns the symptoms and
  the recovery.

## When a run fails

Nobody is alerted. The Bloom run panel is the only signal
([#18](https://github.com/talmolab/sleap-roots-pipeline/issues/18), closed), and the panel's live
updates depend on Bloom Realtime
([bloom#939](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/939)).

**Look quickly.** Bloom submits every cyl Workflow with a `ttlStrategy` of
`WORKFLOWS_K8S_TTL_SECONDS` (Bloom's shipped default is an hour). So the Workflow is deleted at
most that long after it completes, and its pods and logs may go sooner
([#137](https://github.com/talmolab/sleap-roots-pipeline/issues/137)).

- **Inside that window:** `argo get` shows which step failed. Pod logs need the `bloom-pipeline`
  kubeconfig, because `argo-user` cannot read them, and nobody can exec. The step-by-step is
  [ci-debug, section A](../../.claude/commands/ci-debug.md).
- **After it:** what remains is the Bloom run's per-scan results (status and error message) and
  the files on the environment's stage tree. Bloom keeps no copy of cyl pod logs.

**Reading the outcome.** Each producer exits `0` (all scans ok), `3` (the batch completed and some
scans failed in isolation) or anything else (a crash). The exit gate re-derives the run's phase
from those codes; see its
[template header](../../sleap-roots-exit-gate-template.yaml). Three open Bloom issues change what
you see:

- a partial predictor or traits batch still ends the Workflow `Failed` at write-back
  ([bloom#859](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/859));
- a green run with failed scans reads `complete`, not `partial`
  ([bloom#857](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/857));
- a run whose Workflow is gone can stay unfinished in Bloom
  ([bloom#1042](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/1042)).

A `Failed` Workflow does not mean nothing was written.

## Standing operator rules

- **After any Argo or Run:ai upgrade, re-verify the predictor's GPU container reorder**
  ([#127](https://github.com/talmolab/sleap-roots-pipeline/issues/127)). The predictor template's
  `podSpecPatch` comment says why.
- **Run the check suites from Git Bash, not PowerShell.** PowerShell's `bash` is WSL's, and the
  manifest gate then fails for the wrong reason
  ([#128](https://github.com/talmolab/sleap-roots-pipeline/issues/128);
  [`openspec/project.md`](../../openspec/project.md), Testing Strategy).
- **Never point a run with no run id at either shared tree,** `a4_poc` (staging) or
  `bloom_cyl_pipeline/prod` (prod). That covers any bloomctl, predict or traits run outside Argo.
  Such a run writes the legacy `run_manifest.json`, which readers still honour. Use a scratch
  tree. The rule and its reasons are in the roadmap's "Step 7 … is hardening"
  ([roadmap](roadmap.md)).
- **Never run a pre-a9 bloomctl image against the shared trees,** whether hand-submitted or rolled
  back. The drift check cannot see an image inlined in a hand-submitted Workflow.
