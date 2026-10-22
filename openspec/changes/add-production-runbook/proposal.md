# Change: Add a production runbook for the cyl pipeline (#132)

## Why

Bloom production has dispatched through this repo's shared templates since 2026-10-04, and nobody
is alerted when a run fails (#18 closed). What an operator needs is scattered across many
sources: the roadmap, `docs/cluster-identities.md`, template comments, `/tdd`, `ci-debug`, the
semaphore header, and issues. Several of those copies disagree, and some are now false.

## What Changes

- **ADD `docs/bloom-integration/operations.md`,** one page with #132's six sections in order.
  - **It is the canonical home of the guard procedure** for any change that reaches both
    environments. The steps:
    1. idle by `.status.phase` (Running, Pending or no phase);
    2. save a rollback copy;
    3. run the drift check;
    4. apply in the order the template comments give;
    5. read back `image:` and the digest env var;
    6. run the drift check again;
    7. re-check idle.
  - **Every other rule links its owner** and restates nothing.
  - **No tags, digests or SHAs.** It tells the operator to re-derive live pins with
    `scripts/check_cluster_drift.sh` (noting #109).
  - **It records the failure-evidence window** (`WORKFLOWS_K8S_TTL_SECONDS`, #137) and links the
    Bloom issues that change what a failed run looks like.
- **Inbound links:**
  - README: the shared-namespace callout and Troubleshooting.
  - Roadmap: the "Shared templates" hard constraint, which keeps only the reach fact, and frontier
    item 10, where "No prod runbook exists" is rewritten.
  - `cluster-identities.md` "Related".
  - `/tdd` "Live acceptance tests" and `openspec/project.md` "Live acceptance", which link the guard
    instead of restating it.
  - `.claude/commands/test.md`'s table of files the suites read.
- **Claim-wide corrections** (owner decision (a), 2026-10-16). These touch docs, script header
  comments and template comments; the parsed YAML is unchanged, so nothing is deployed.
  - **Shared-tree hazards:**
    - the no-run-id operator rule names both environments' trees;
    - the "Deliberate" pre-a9 rollback bullet names the prod tree;
    - the 2026-09-21 design spec's two restatements point at the roadmap rule;
    - runai SKILL §6 links the rule.
  - **A missing `hostPath` hangs Pending.** Fixed in `openspec/project.md` (two places), README
    "Configuring Volume Paths", and `ci-debug.md` (two rows, including its `retryStrategy` advice).
  - **Failure evidence, access, manifests and environments:**
    - the #137 window in `cluster-identities.md`, `ci-debug.md` §A and README Troubleshooting;
    - `argo-user`'s `get`/`list`/`watch workflows`;
    - README's crash bullet and the predictor template's comments, both rewritten for per-run
      manifests;
    - `runai_run_pipeline.sh`'s header ("distinguished only by an environment label").
  - **The unlink procedure.** The trait-extractor rollback comment says `unlink()` also drops
    `candidate` and `latest`. The predictor comment says the cards are linked.
- **ADD `check_docs.py` assertions,** red first, for each item above.

## Impact

- **Affected specs:**
  - `cluster-access-docs`: ADDED, two requirements;
  - `per-batch-pipeline`: MODIFIED, "Every producer carries the Argo workflow identity",
    rationale wording only.
- **Affected files:**
  - `docs/bloom-integration/operations.md` (new);
  - `scripts/check_docs.py`, `README.md`, `docs/bloom-integration/roadmap.md`,
    `docs/cluster-identities.md`, `openspec/project.md`;
  - `.claude/commands/ci-debug.md`, `.claude/commands/tdd.md`, `.claude/commands/test.md`,
    `.claude/skills/runai/SKILL.md`;
  - `docs/superpowers/specs/2026-09-21-per-run-run-manifest-identity-design.md`;
  - `sleap-roots-trait-extractor-template.yaml` and `sleap-roots-predictor-template.yaml`
    (comments only);
  - `runai_run_pipeline.sh` (header comment only).
- **Not here:** the status dashboard (open PR #136 edits it), which is a post-merge refresh.
- **Refs:** #132 (closes), #137, #18, #63, #106, #109, #127, #128; bloom#857, #859, #939, #983,
  #988, #1042; training#72.
