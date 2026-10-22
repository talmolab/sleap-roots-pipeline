# Operating the cyl pipeline in production

This page is for whoever changes, rolls back or debugs the pipeline now that Bloom production
dispatches through it (live since 2026-10-04). It owns one procedure, the guard in the first
section. For everything else it gives the rule in a sentence or two and links the source that owns
the detail. Follow the link rather than a copy: the sources are kept current, and this page
deliberately holds no image tags, digests or commit SHAs.

**Where to run the commands.** Use an interactive WSL shell under the `argo-user` kubeconfig:

```bash
export PATH=$HOME/bin:$PATH KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
cd /mnt/c/repos/sleap-roots-pipeline   # an up-to-date main checkout
```

Don't paste the snippets through `wsl -e bash -c "…"` from PowerShell. PowerShell expands the `$`s
first, and the idle check would then silently pass. Where the CLIs live is in
[the runai skill, §1a](../../.claude/skills/runai/SKILL.md).

## Before any change to the cluster

Bloom staging and prod run on the same `sleap-roots-*` WorkflowTemplates, the same semaphore
ConfigMap and the same model registry (see
[Cluster identities → Namespace facts that bite](../cluster-identities.md#namespace-facts-that-bite)).
So two kinds of change reach **both** environments at once:

- **Template updates.** Every `argo template update`, whether a deploy or a rollback.
- **Registry links.** Every registry `production` link or unlink.

Retuning the semaphore limits is separate; its procedure is in the
[ConfigMap header](../../sleap-roots-pipeline-semaphores.yaml).

**`runai_run_pipeline.sh` is not a deploy path.** It updates all five templates at once, in a
fixed order that ignores the order the template comments require. It can't re-check idle between
updates. It then submits its own hand-run Workflow on the staging tree. Use it for a hand run only
when the drift check already reports `IN SYNC`.

The guard:

1. **Work from `main`.** Never register a template from an unmerged branch. The drift check
   compares the cluster against your checkout, so the checkout must be an up-to-date `main`.
2. **Confirm nothing is in flight.** Prod users can dispatch at any time.
   - Read each Workflow's `.status.phase`.
   - Count a Workflow with no phase as in flight.
   - Match on the templates it references, not only its name, so a hand-submitted run on the same
     templates counts.
   - Fail closed if the list itself fails.

   Don't line-count `argo list --running -o name`: it prints `No workflows found` when there are
   none, which once aborted a deploy on a false positive (roadmap status log, 2026-10-02
   (deploy)). Define this once per shell:

   ```bash
   srp_idle() (
     set -o pipefail
     rows=$(kubectl get workflows -n runai-busch-lab -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.phase}{"\t"}{.spec.templates[*].dag.tasks[*].templateRef.name}{"\n"}{end}') \
       || { echo "could not list workflows: NOT checked" >&2; return 1; }
     busy=$(printf '%s\n' "$rows" | awk -F'\t' '($1 ~ /^sleap-roots-/ || $3 ~ /(^| )sleap-roots-/) && ($2=="" || $2=="Running" || $2=="Pending")') \
       || { echo "filter failed: NOT checked" >&2; return 1; }
     [ -z "$busy" ] || { printf 'in flight:\n%s\n' "$busy" >&2; return 1; }
     echo "idle: no sleap-roots Workflow Running, Pending or without a phase"
   )
   srp_idle
   ```

   This can't see a batch Bloom has claimed but not yet submitted. Step 8 covers that window.
3. **Save a rollback copy** of each template you will change, outside the repo:

   ```bash
   d=~/srp-rollback/$(date +%Y%m%dT%H%M%S); mkdir -p "$d"
   kubectl get workflowtemplate <name> -n runai-busch-lab -o yaml > "$d/<name>.yaml" \
     && [ -s "$d/<name>.yaml" ] || echo "ROLLBACK COPY FAILED" >&2
   ```

4. **Run the drift check:** `bash scripts/check_cluster_drift.sh`. Expect `DRIFT` only on the
   templates you are about to change, and only in the fields you mean to change. A `NOT
   REGISTERED` can also mean a failed read
   ([#109](https://github.com/talmolab/sleap-roots-pipeline/issues/109)).
5. **Apply one template at a time, in the order the template comments give,** re-checking idle in
   the same command:

   ```bash
   srp_idle && argo template update <file> -n runai-busch-lab
   ```

   Some pairs must not be applied in the wrong order. For example, write-back goes before
   images-downloader on a bloomctl bump that changes the manifest writer.
6. **Read back what is live.** For each changed template, compare the live image with the repo.
   On the predictor or trait-extractor, also compare `SRP_PREDICT_CONTAINER_DIGEST` or
   `SRT_TRAITS_CONTAINER_DIGEST`:

   ```bash
   kubectl get workflowtemplate <name> -n runai-busch-lab -o jsonpath='{.spec.templates[0].container.image}{"\n"}{range .spec.templates[0].container.env[?(@.name=="SRP_PREDICT_CONTAINER_DIGEST")]}{.name}={.value}{"\n"}{end}{range .spec.templates[0].container.env[?(@.name=="SRT_TRAITS_CONTAINER_DIGEST")]}{.name}={.value}{"\n"}{end}'
   ```

7. **Run the drift check again.** Expect `IN SYNC` for every template and the ConfigMap. The
   comparison uses parsed YAML, so a comment-only change never drifts and needs no deploy.
8. **Run `srp_idle` again.** The idle check holds only for the moment it ran. If a run started
   during the change, note which images it ran.

**To restore a rollback copy:** `argo template update "$d/<name>.yaml" -n runai-busch-lab`. Run
it through steps 2 and 4–8, like any other change.

**A registry `production` link or unlink takes steps 2 and 8:** `srp_idle` immediately before the
link and again right after. The link's own procedure lives with the training repo's issue for it,
for example [training#72](https://github.com/talmolab/sleap-roots-training/issues/72).

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
2. **For the predictor and trait-extractor, start at the trait-extractor template's `Rollback`
   comment**
   ([`sleap-roots-trait-extractor-template.yaml`](../../sleap-roots-trait-extractor-template.yaml)).
   It lists each rollback layer in order: what to unlink in the registry first, which rollback
   moves only traits, and which also moves predict, as the
   [`sleap-roots-predictor-template.yaml`](../../sleap-roots-predictor-template.yaml) comment
   explains. Re-pin the tag, the digest and the digest env var together.
3. **For bloomctl:** the exit-gate, images-downloader and write-back templates move together.
   Roll them back to the **last** `Rollback target:` in the
   [`sleap-roots-images-downloader-template.yaml`](../../sleap-roots-images-downloader-template.yaml)
   header, in the order that bump's paragraph gives.
4. **Never go below the a9 floor.** That rollback was retired on 2026-10-22, because a pre-a9
   bloomctl image would start a cumulative legacy `run_manifest.json` in both environments' trees
   (roadmap, "Step 7 … is hardening", the "Deliberate" bullet: [roadmap](roadmap.md)). Recover from
   a broken a9-era image by rolling back to an earlier a9 target, or by fixing forward.
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
- a run whose Workflow was deleted before Bloom saw it finish used to stay unfinished. The fix
  ([bloom#1045](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/1045) and
  [bloom#1048](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/pull/1048)) is deployed
  to both environments (both 2026-10-21 Bloom deploys contain it). The issue stays open until the
  fix is verified ([bloom#1042](https://github.com/Salk-Harnessing-Plants-Initiative/bloom/issues/1042)).
  If a run still sits unfinished after its Workflow is gone, report it there.

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
  bloomctl then writes the legacy `run_manifest.json`, which readers still honour. predict and
  traits forward a manifest that is already there, and otherwise run unscoped over the whole input
  tree. Use a scratch tree. The rule and its reasons are in the roadmap's "Step 7 … is hardening"
  ([roadmap](roadmap.md)).
- **Never run a pre-a9 bloomctl image against the shared trees,** whether hand-submitted or rolled
  back. The drift check cannot see an image inlined in a hand-submitted Workflow.
