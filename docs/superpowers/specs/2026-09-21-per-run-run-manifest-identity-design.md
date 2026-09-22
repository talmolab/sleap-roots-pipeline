# Per-run run-manifest identity — design

**Date:** 2026-09-21
**Issue:** [sleap-roots-pipeline#71](https://github.com/talmolab/sleap-roots-pipeline/issues/71)
**Status:** approved design, not yet implemented
**Audience:** whoever implements or reviews this change across the five repos — it is the
authority the five OpenSpec proposals are written against.

Every code fact below was read in the working tree on 2026-09-21 and is cited with a line
number. Where this document contradicts an issue or a handoff, the contradiction is called out
explicitly rather than silently corrected.

## 1. The defect

`write_run_manifest` (`salk-bloom` `bloomcli/src/bloomctl/cyl/download_for_predict.py:458`)
unions this invocation's usable `scan_keys` into any existing `run_manifest.json` and never
prunes. srp#37 separately established that `out_dir` is permanently shared across all runs *by
design* — isolating it would break the cluster-side skip-if-done that the A4 batch-oracle target
depends on. The two facts together mean the manifest accumulates the keys of every run that has
ever used those directories, and every stage downstream scopes itself to that union.

Measured four times on 2026-09-21 against current pins, including through the real Bloom
dispatch path:

| run | requested | manifest carried | envelopes delivered |
|---|---|---|---|
| `sleap-roots-pipeline-9s92h` | 2 | 10 | 10 |
| `sleap-roots-pipeline-p6lz2` (Bloom-dispatched) | 3 | 12 | 12 |
| `sleap-roots-pipeline-hpdpf` | 1 | 12 | 12 |

A one-scan request created `cyl_trait_sources` rows for eleven scans nobody requested. This
reaches persisted state in Bloom, which is why it is being fixed before the Bloom UI (bloom#15)
builds a progress panel on per-run counts the manifest can inflate.

### Constraints inherited from the issue

- **Cannot isolate paths.** srp#37 established that this breaks skip-if-done and the batch oracle.
- **Cannot stop merging** without first establishing that nothing still needs the merge (§2.1).
- **Cannot fix it by preserving `pipeline_run_id`.** A single id for a key set spanning runs is
  the wrong shape whichever value wins.

Fix shape **(a)** from the issue — per-run manifest *identity*, shared artifacts — was already
selected there over **(b)** (one file with per-key attribution, which needs a breaking
`RunManifest` change). This design does not relitigate that.

## 2. Decisions taken

### 2.1 predict#40 is dissolved by this change, not merely adjacent to it

srp#71's third comment and predict#40's cross-link comment both assert that #71's fix does *not*
remove the need for #40, on the grounds that "one logical request still chunks across K
concurrent invocations sharing an `out_dir`, so the merge-under-lock is still required — just
scoped to one file." **The premise is half right and the conclusion does not follow.**

The K chunks do share an `out_dir`. They do **not** share a workflow identity:

- `services/workflows/pipeline.py:311` chunks the request at `BATCH_SIZE = 25` and enqueues each
  batch separately.
- `services/workflows/dispatch_worker.py:89-90` calls `build_workflow_body` then
  `submit_workflow` **once per batch** — one Argo Workflow per chunk, not one workflow with a
  fan-out.
- `sleap-roots-pipeline.yaml:27` is `generateName: sleap-roots-pipeline-`, so each submission
  gets its own unique `{{workflow.name}}`.
- `sleap-roots-pipeline.yaml:95-165` is a strictly linear DAG — `images-downloader` →
  `predictor` → `trait-extractor` → `write-back` → `exit-gate`, no `withParam` or `withItems` —
  so within one workflow each stage runs exactly once.

Therefore once the manifest is named per run id, two concurrent chunks write
`run_manifest.<A>.json` and `run_manifest.<B>.json`. They never open the same path. The
read-merge-write race disappears, the union has nothing left to union, and both naive-overwrite
forwarding hops stop being racy. The temp-file hazard goes with it: `sleap-roots`' fixed
`run_manifest.json.tmp` becomes `run_manifest.<id>.json.tmp`, unique per run.

**Decision:** land #71 alone. Post the evidence above to predict#40 and narrow it to its two
genuine residues — `sleap-roots`' missing temp-file cleanup, and the unexamined NFS
`O_CREAT|O_EXCL` question, which belongs to the *staging* lock that this change does not touch.

### 2.2 A missing manifest fails loud where the run id is known

Today a missing manifest means unscoped discovery over the whole shared directory, in all three
readers:

| reader | behavior when the manifest is absent |
|---|---|
| `bloomctl` `ingest.py:116` | `return DiscoveredEnvelopes(paths=all_paths, missing_scan_keys=[])` — every envelope |
| `sleap-roots-predict` `batch.py:90` `discover_scans` | every sidecar found |
| `sleap-roots` `extractor.py:195` | `scope = None`, then walks every `*.predictions.json` |

Per-run naming makes "my manifest is missing" far more reachable — any mid-rollout pin skew
produces it — and the failure is silent and *widens* scope rather than narrowing it. That is
strictly worse than the bug being fixed.

`ARGO_WORKFLOW_NAME` is the discriminator. Set means the stage knows which run it is, so a
missing manifest is a real fault. Unset means local/dev, where unscoped discovery is established
behavior that predict's own test assets depend on (`tests/assets/scans/` deliberately stages no
`run_manifest.json`).

**Decision:** resolution order is (1) `run_manifest.<own id>.json`, (2) legacy
`run_manifest.json`, (3) if the run id is known, **raise**; if not, return `None` and keep
today's unscoped behavior.

### 2.3 Per-run naming is keyed to Argo

`resolve_pipeline_run_id()` (`download_for_predict.py:448`) returns `ARGO_WORKFLOW_NAME` when
set, else a per-invocation `local-<uuid8>` placeholder. A reader cannot reproduce another
process's placeholder, so keying the *filename* on it would break local scoping end to end.

**Decision:** when `ARGO_WORKFLOW_NAME` is unset, the writer uses the legacy unsuffixed
filename and every reader falls through to it. Local and `local-WSL2-*` runs therefore behave
exactly as they do today, with no template plumbing and no new failure mode. The `local-<uuid8>`
value still goes *inside* the file as `pipeline_run_id`, so manual runs stay distinguishable.

This is why the `local-WSL2-*` templates are deliberately **not** given `ARGO_WORKFLOW_NAME`.

### 2.4 The writer overwrites its own file rather than unioning into it

Per-run naming fixes the cross-run half on its own. Within a run the only other writer is a
`retryStrategy` re-run of `images-downloader` (retry strategies are present on every cluster
template). Unioning there would retain a key from a failed earlier attempt that has no
`result.json` — which is bloom#859's latch surviving inside a single run.

**Decision:** write this invocation's usable keys, not a union with what is already there.
"What this invocation found usable" is the truthful record and removes the latch outright.

**The manifest lock is retained.** It costs nothing, it is already specified and tested, and
removing it means deleting a requirement plus its scenarios from `salk-bloom`'s
`cyl-batch-download-for-predict` spec on code with a documented regression history. Its removal
is a separate cleanup, filed, not part of this change.

### 2.5 The forwarding hops forward under the name they read

The hops do not need to know their own run id. Whatever name the downloader wrote propagates
unchanged through `predictions/` and `traits/` to write-back, so any mid-rollout fleet state is
self-consistent by construction.

### 2.6 predict#34 is a prerequisite, packaged separately

`sleap-roots-contracts` is at **0.1.0a8** (tagged; `origin/main` `39cb09b`), so this change ships
as **0.1.0a9**. a8 is a breaking reshape: `ModelCard.species/mode/age_min/age_max` were replaced
by `ModelCard.selectors: tuple[Selector, ...]`.

| consumer | pin | affected by the a8 reshape |
|---|---|---|
| `sleap-roots-predict` | `==0.1.0a7` | **yes** — 13 sites in `model_selection.py:86-88` and `parity.py`, 69 references across 8 test files |
| `sleap-roots` (traits) | `==0.1.0a7` (×3) | no — imports no `ModelCard` |
| `bloomctl` | `>=0.1.0a7` | no — imports no `ModelCard` |

`model_selection.py` is on the container's runtime path, not a dev-only tool. The migration is
already filed as **predict#34**, open since 2026-08-12; nothing had connected it to this train.

It cannot be sidestepped by reordering, because predict is a reader and readers must precede the
writer flip (§4).

**Decision:** land predict#34 as its own PR first, suite green, predict released. #71's predict
change is then a small diff on top. A breaking change to runtime model selection does not belong
hidden inside a correctness fix.

### 2.7 The W&B registry must be re-seeded before predict is *deployed*

predict#34 is not only a code migration. Model cards are **data in W&B**, read by
`WandbRegistrySource.list_cards` (`sleap_roots_predict/model_registry.py`) from
`<entity>-org/wandb-registry-sleap-roots-models`, filtered to the `production` alias and
validated against `ModelCard`.

Contracts a8 states the incompatibility as a deliberate choice:

> There is deliberately **no tolerant read** of the legacy flat shape (a card-level
> `species`/`mode`/`age_min`/`age_max`). Those keys are dropped as ordinary extras and the card
> fails on the missing `selectors`.

**Measured against the live registry on 2026-09-21** (read-only probe, alias `production`):

```
production artifacts: 13   selector-shaped: 0   flat-shaped: 13
```

All thirteen — the exact 13 registrations training#39 describes, backed by 8 physical models —
are still flat. The producer-side code shipped (**training#47**, merged 2026-08-26) but the
**re-seed itself has not been run**, which is why training#39 is still open.

**The failure mode is quiet.** `list_cards` skips an artifact that fails validation with a logged
warning and continues, per artifact, by design (predict#32). An upgraded predict against today's
registry therefore skips all 13, returns an **empty catalog**, and cannot select any model —
there is no single loud error saying the registry is the problem.

Consequences for this train:

- The re-seed is a **prerequisite of the predictor pin bump**, not of the merge. predict#34 may
  be merged and pinned at any time; only the deploy is ordered (§4).
- The old flat collections must keep their `production` alias until predict's upgrade is
  confirmed **deployed**, not merely merged — they are the only thing an un-upgraded deployment
  can read.

### 2.8 The re-seed is ours to run, and it brackets this rollout

The re-seed is already fully specified as **group 6 of `update-model-card-selectors`** in
`sleap-roots-training` — a change that is merged but **deliberately not archived**, with 65 of 73
tasks ticked and group 6 left open as "Migration — gated, and a separate PR after this change
archives". We own it; nothing needs designing, only executing.

Confirmed available on 2026-09-21:

- The tooling: `sleap-roots-training seed-registry`, with `--only` (canary), `--verify`
  (read-only), `--execute`, `--force`. Dry run is the default and makes no wandb calls.
- The inputs: `--execute` requires `--models-root`, a tree of `<model_id>.zip` archives, and
  **rejects an already-unzipped directory**. The required snapshot — models-downloader's
  `20250204_models`, the matrix's declared source of truth — is present locally at
  `c:\repos\models-downloader\tests\data\models_downloader_input\20250204_models\`, zips and
  `model_chooser_table.xlsx` included.

**It brackets this rollout rather than merely preceding it**, which is the part that matters for
ordering. Group 6's own text:

> The re-seed runs **before** the upgraded predict is deployed [...] During the window the two
> consumer generations are cleanly partitioned: an un-upgraded predict reads the 13 old
> collections and skips the 8 new ones as unparseable, and an upgraded predict does exactly the
> inverse. Neither ever sees two cards for one context [...] Retirement (6.3) is what ends the
> un-upgraded generation's access, which is why it stays gated on confirmed deployment.

So the re-seed (6.0–6.2) goes **before** the predictor deploy and the retirement (6.3) **after**
it. The dual-aliased window in between is the designed safe state, not a hazard to minimise.

Two operational constraints carried from that document:

- **Single-operator.** `_existing_collections` is read once up front (`publish.py:146`), so two
  concurrent `--execute` runs both see a collection as absent, both publish, and the alias lands
  wherever `link_artifact` ran last — both reporting success. Announce the window; re-run
  `--verify` immediately before 6.3.
- **Not revertable.** A live wandb re-seed is not `git revert`-able, and a collection must
  **never** be deleted. Rollback for an additive re-seed is removing `production` from the *new*
  collections, rehearsed on the canary first (6.0).
- **Every idempotency key changes.** `registry_id` changes for all 8 models under the producer's
  new collection-id scheme, and `compute_idempotency_key`
  (`sleap-roots-contracts/src/sleap_roots_contracts/identity.py:44-45`) hashes
  `(registry_id, version, weights_checksum)` per model. The first run after the migration
  therefore recomputes every scan rather than reusing anything. This is a one-time re-baseline of
  the A4 batch-oracle property, and it is expected, not a regression (§5).

## 3. Mechanism

### 3.1 `sleap-roots-contracts` (the enabling change)

`src/sleap_roots_contracts/run_manifest.py` gains three names, all exported from the package
root:

```python
def run_manifest_filename(pipeline_run_id: str) -> str:
    """Return "run_manifest.<pipeline_run_id>.json"."""

def pipeline_run_id_from_env() -> str | None:
    """ARGO_WORKFLOW_NAME, or None when unset/blank."""

def resolve_run_manifest_path(directory, pipeline_run_id: str | None) -> Path | None:
    """§2.2's resolution order. Raises when the run id is known and neither file exists."""
```

`RUN_MANIFEST_FILENAME` is unchanged and retained as the legacy/local name.

`run_manifest_filename` **validates that the id is filename-safe** — it arrives from an
environment variable and becomes a path component, so path separators, `..`, and empty/blank are
rejected. An Argo workflow name is an RFC-1123 label, so nothing legitimate is excluded.

The resolution *policy* lives in contracts rather than being reimplemented three times. Three
independent copies of a three-branch rule across four repos is precisely how this program's
normative text drifts, and single-definition was predict#40's actual goal, minus the lock.

`resolve_run_manifest_path` touches the filesystem, which is a departure for a library that is
otherwise pure models and constants. That is a deliberate, contained exception: the alternative
is three copies of the branch that matters most for correctness.

### 3.2 Cross-check, free of charge

When a reader loads a *per-run-named* file, it asserts `manifest.pipeline_run_id` equals its own
run id. This is bloom#703's cross-check, possible for the first time — the field could never
disagree before, because the writer unconditionally overwrote it with the current run's value.

### 3.3 Call sites

| repo | file | change |
|---|---|---|
| `salk-bloom` | `download_for_predict.py:458` | write to the resolved per-run path; overwrite, not union (§2.4) |
| `sleap-roots-predict` | `run_manifest.py:99`, `batch.py:90`,`:286` | resolve via contracts; forward under the name read (§2.5) |
| `sleap-roots` | `trait_extractor/run_manifest.py:17`,`:48`, `extractor.py:142` | same; plus temp-file cleanup on failure |
| `salk-bloom` | `ingest.py:91-116` | resolve via contracts; fail loud instead of returning every envelope |

## 4. Rollout — order is load-bearing

**Readers must land before the writer.** If `bloomctl` flips first, an un-bumped predict looks
for the legacy name, finds nothing, and falls through to unscoped discovery over the entire
shared directory — briefly worse than the defect being fixed.

One seam makes this clean: `images-downloader`, `write-back` and `exit-gate` all run the **same**
`bloomctl:sha-28034f6` image, so a single pin bump flips the writer and the write-back reader
together, with no intermediate state.

The registry migration (§2.8) interleaves with it, so the two are written as one sequence. Steps
0a–0e are prerequisite work in *other* repos; #71's own train is steps 1–5.

0a. **predict#34** — a8/`Selector` migration in predict. Merge, pin contracts a8, suite green.
   Merging is ungated; only the deploy (0c) is ordered.
0b. **Re-seed the W&B registry** — training tasks 6.0–6.2: rollback prep and snapshot of the 13
   current collection→version mappings; canary one collection with `--only` and prove an
   upgraded predict resolves it *and* an un-upgraded one still resolves the old card; then the
   remaining 7; then a full `--verify` reporting **exactly 13 orphans**. Registry is now
   dual-shaped, generations cleanly partitioned (§2.8).
0c. **Deploy predict#34** — predictor image build and pin bump in this repo. One falsifiable
   question: does model selection still resolve, now against the new collections. Keeping this
   deploy separate from step 2 is the whole point — an empty catalog is silent (§2.7), so it
   must not share a deploy with the manifest change.
0d. **Retire the 13 flat collections** — training task 6.3, gated on 0c being *confirmed
   deployed*, not merely merged. Acceptance: `--verify` reports zero orphans and zero
   legacy-shape expected collections.
0e. **Close out training** — tasks 6.4 (comment the outcome on training#39, plus the correction
   its 2026-08-10 comment needs), 6.5, then the archive PR with 6.6's spec-ordering fix.
1. **contracts 0.1.0a9** — purely additive; nothing breaks.
2. **predict + traits** — adopt, release, rebuild images, bump their two template pins. The
   fleet still reads legacy manifests written by the old `bloomctl`; **no manifest behavior
   change yet.**
3. **bloomctl** — writer flips to the per-run name, `ingest` dual-reads. One image, one pin bump
   across three templates. **This is the flip.**
4. **`argo template update`** for all five templates.
5. **Delete the three stale `run_manifest.json` files** under the `a4_poc` directories.
   Otherwise a run whose downloader failed to write falls back onto a stale 12-key manifest —
   today's bug, resurrected through the very fallback added to make the rollout safe.

Every pin bump is production-visible: `runai-busch-lab` is shared by Bloom staging and
production (`services/workflows/k8s_client.py` docstring). Production is dormant but live.

## 5. Verification

Unit tests in each repo, TDD, before the live run.

Live acceptance, Bloom-dispatched (not `argo submit`, so `done_count`/`failed_count` are real):
dispatch against staging experiment `A4-PIPELINE-E2E-TEST` (`experiment_id` 12880747; scans
12894756–12894759 good, 12894760 poison) at **N=1** and **N=3**, and assert

- the manifest holds **exactly N** `scan_keys`,
- write-back reports **`Ingested N/N`**,
- `cyl_trait_sources` gains **exactly N** rows.

Today any such run reports 10–12 regardless of N, so the test fails before the change and passes
after it.

Known noise, not regressions: bloom#875's residue makes sources whose first delivery was
hand-submitted report `failed`; write-back's `Ingested 0/N` headline counts only `status == "ok"`
and understates success.

**Expect no skip-if-done reuse on the first run after the registry migration.** Every
idempotency key changes with `registry_id` (§2.7), so the first post-migration run does real GPU
work on scans that would previously have been skipped. This does not affect the assertions above
— they count manifest keys, ingested envelopes and DB rows, not skips — but it does mean the
batch-oracle "re-run an already-done batch → 0 GPU pods" check must be re-baselined *after* the
migration rather than compared across it.

## 6. Risks

| risk | mitigation |
|---|---|
| Mid-rollout skew silently widens scope | reader-first ordering (§4) + fail-loud (§2.2) |
| Stale legacy manifests reachable through the fallback | delete them at step 5 |
| `pipeline_run_id` is environment-supplied and becomes a path component | validated in `run_manifest_filename` (§3.1) |
| Per-run manifests accumulate, one per run per directory, forever | small files; GC filed as follow-up |
| Production-visible template update | production dormant; staging validated first |
| Predictor pinned before the W&B re-seed → empty model catalog, warnings only | step 0a gates the predictor pin bump (§2.7) |
| Idempotency keys all change with `registry_id` → one-time full recompute | expected; re-baseline the batch oracle after the migration (§5) |

## 7. Deliverables beyond code

These are part of this change, but are not code:

- The correcting comment on predict#40 (§2.1), narrowing it to its two genuine residues.
- The roadmap entry in `docs/bloom-integration/roadmap.md`, recording what was observed after
  the fact.
- The `sleap-roots-training` migration PR — group 6's tasks ticked, the 6.0(a) baseline snapshot
  committed, and `openspec archive` run (§2.8, §4 steps 0b/0d/0e). That PR runs no CI, since
  `openspec/**` is outside `ci.yml`'s path filters.

**Repos touched, and why:** `sleap-roots-contracts` (the helper), `salk-bloom` (writer +
write-back reader), `sleap-roots-predict` (reader/forwarder, plus prerequisite #34),
`sleap-roots` (reader/forwarder), `sleap-roots-pipeline` (pin bumps, roadmap, this doc) and
`sleap-roots-training` (the registry migration) — six, not the four the issue anticipated.

## 8. Out of scope — to be filed as follow-ups

- Removing the legacy-name fallback once the fleet is confirmed migrated (needs a second train).
- GC of accumulated per-run manifests.
- Removal of the now-redundant manifest lock (§2.4).
