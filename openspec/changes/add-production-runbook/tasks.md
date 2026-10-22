# Tasks

Red-first (`openspec/project.md`, "tasks.md conventions"; `/tdd`).

**Each numbered section 1–5 is one commit.** Its first task adds assertions to
`scripts/check_docs.py` and runs the suite; the run must be red for the stated reason. Its second
task edits the docs to green. The commit holds both, the quoted FAIL lines go in its body, and the
section's tasks are ticked in it. **Never commit a red suite.**

**Commands** (Git Bash, per #128):
- Suite: `uv run --no-project --with pyyaml bash scripts/check_all.sh`
- Lint: `wsl -e bash scripts/lint_manifests.sh`

**Helpers** (added in section 1, reused after):
- `text_or_empty(path)`: returns `""` for a missing file, so a check FAILs instead of crashing.
- `between(text, start, end)`: the slice from `start` up to `end`. Each use first checks that both
  anchors are found (`... anchors found: got False, expected True`).
- `md_section(page, heading)`: from `## <heading>\n` up to the next `\n## ` heading of any kind.
- `comment_block(path, anchor)`: the `#` comment lines from the anchor line up to the first
  non-comment line, with `#` stripped, then normalised.

All file collections are ordered lists. "Links X" means a markdown link `](<relative path to X>`,
not a mention. No live-cluster behavior changes, so there is no red baseline or acceptance task.

## 0. Proposal (commit `docs(openspec): propose add-production-runbook (#132)`)

- [x] 0.1 Commit this change directory after user approval, before any `check_docs.py` edit. The
  commit body records:
  - the two `/review-openspec` rounds: 2026-10-04 (BLOCKED) and 2026-10-16 (BLOCKED, then revised);
  - the owner's scope decision, option (a), 2026-10-16.

## 1. Shared-tree hazards (cluster-access-docs Req 2: The no-run-id rule covers both shared trees)

- [x] 1.1 Add the assertions:
  - **Rule anchor:** `never point a no-run-id` appears exactly once in the roadmap.
  - **Rule text:** take `between(roadmap_n, "never point a no-run-id", "use a scratch tree")`. It
    contains `a4_poc` and contains `bloom_cyl_pipeline/prod`.
  - **Deliberate bullet:** take `between(roadmap_n, "**Deliberate:** a bloomctl rollback",
    "- **Covered:**")`. It contains `bloom_cyl_pipeline/prod`.
  - **No a4_poc-only copies:** check over the files `[ROADMAP, PER_RUN_SPEC, SKILL]` (in that order)
    for normalised text matching ``shared `a4_poc` trees?(?![^.]*bloom_cyl_pipeline/prod)``. Want `[]`. Section 5 adds the
    runbook to this list.
  - **SKILL §6:** `between(skill_raw, "## 6.", "## 7.")` contains `no-run-id` and
    `](../../../docs/bloom-integration/roadmap.md`.

  Validate (red), expecting exactly:
  - `FAIL  roadmap: no-run-id rule names prod's shared tree: got False, expected True`
  - `FAIL  roadmap: Deliberate rollback bullet names bloom_cyl_pipeline/prod: got False, expected True`
  - `FAIL  no doc limits the no-run-id rule to a4_poc: got ['docs/bloom-integration/roadmap.md',
    'docs/superpowers/specs/2026-09-21-per-run-run-manifest-identity-design.md'], expected []`
  - `FAIL  runai SKILL §6 names the no-run-id rule: got False, expected True`
  - `FAIL  runai SKILL §6 links the roadmap rule: got False, expected True`
- [x] 1.2 Make the doc edits:
  - **Roadmap operator rule:** widen it, and its "Reopen #82 if … appears there", to both trees,
    writing `bloom_cyl_pipeline/prod` literally.
  - **Roadmap "Deliberate" bullet:** add that a rollback below the a9 floor also runs the pre-a9
    writer against `bloom_cyl_pipeline/prod`. That tree never held a legacy `run_manifest.json`,
    so the writer would start a new cumulative one there, with nothing to restore.
  - **Design spec's two superseded notes:** replace the a4_poc parenthetical with a pointer to the
    roadmap's "Step 7 … is hardening" rule.
  - **SKILL §6:** add one line: this is a no-run-id run, so keep it off both shared trees, with a
    link to the roadmap rule.

  Validate: 1.1 PASSes; the suite is green.

## 2. A missing hostPath hangs Pending (cluster-access-docs Req 2: A missing hostPath is described as Pending)

- [x] 2.1 Add the assertions:
  - **Startup-failure claims:** check over the files `[PROJECT, README, CI_DEBUG]` for normalised
    text matching `fails? (pod )?startup|fails at startup|startup fails` (case-insensitive). Want
    `[]`. Section 5 adds the runbook to this list.
  - **ci-debug Pending row:** the single line containing `` stuck `Pending` (any stage) `` does not
    contain ``add `retryStrategy` ``, and does contain `cluster-identities.md`.

  Validate (red), expecting exactly:
  - `FAIL  no doc says a missing hostPath fails pod startup: got ['openspec/project.md',
    'README.md', '.claude/commands/ci-debug.md'], expected []`
  - `FAIL  ci-debug: Pending row does not recommend retryStrategy: got True, expected False`
  - `FAIL  ci-debug: Pending row links cluster-identities: got False, expected True`
- [x] 2.2 Rewrite each statement as "the pod stays `Pending` and the Workflow hangs", in:
  - `openspec/project.md:97`;
  - `openspec/project.md:207` (the Important Constraints bullet);
  - `README.md:240`;
  - ci-debug's "Pod fails at startup, volume error" row.

  In ci-debug's Pending row, replace "add `retryStrategy`" with: `retryStrategy` cannot help a
  Pending pod (`cluster-identities.md`); for a pod that can never schedule, see the stalled-slots
  row below.

  Validate: 2.1 PASSes; green.

## 3. Failure evidence, access, manifests, environments (cluster-access-docs Req 2: Failure evidence, access and manifests are stated as observed; per-batch-pipeline MODIFIED)

- [x] 3.1 Add the assertions:
  - **cluster-identities pod-log paragraph:** in the raw text, slice from `**Pod logs need the
    \`bloom-pipeline\` kubeconfig` to the next `\n\n`. It contains `WORKFLOWS_K8S_TTL_SECONDS` or
    `issues/137`.
  - **ci-debug:** `between(ci_debug, "## A.", "## B.")` contains `issues/137`.
  - **README Troubleshooting:** `between(readme_raw, "## 🐛 Troubleshooting", "\n## ")` contains
    `issues/137`.
  - **argo-user row:** the rows of `cluster-identities.md` starting ``| **`argo-user`**`` number
    exactly 1. Its Can cell, `row.strip("|").split("|")[2]`, contains
    `` `get`/`list`/`watch workflows` ``.
  - **No cumulative-manifest claims:** check over `[README, PREDICTOR_TEMPLATE]` for normalised
    text matching `cumulative across every run|accumulates scan_keys[\s#]+across every run`. Want `[]`.
  - **Launcher header:** the raw text of `runai_run_pipeline.sh` does not match
    `distinguished only[\s#]+by an environment label`. The phrase wraps across a `#` comment line.

  Validate (red), expecting exactly:
  - `FAIL  cluster-identities: pod-log paragraph names the TTL window: got False, expected True`
  - `FAIL  ci-debug §A: links #137: got False, expected True`
  - `FAIL  README Troubleshooting: links #137: got False, expected True`
  - `FAIL  cluster-identities: argo-user Can cell lists get/list/watch workflows: got False, expected True`
  - `FAIL  no doc calls the legacy manifest cumulative: got ['README.md',
    'sleap-roots-predictor-template.yaml'], expected []`
  - `FAIL  runai_run_pipeline.sh: environments not 'distinguished only by an environment label':
    got True, expected False`
- [x] 3.2 Make the doc and comment edits:
  - **TTL window:** add it, as "at most `WORKFLOWS_K8S_TTL_SECONDS` after completion; pods may go
    sooner; [#137]", to the cluster-identities pod-log paragraph, ci-debug §A and the top of
    README Troubleshooting.
  - **argo-user row:** add `` `get`/`list`/`watch workflows` `` to the Can cell, with "(verified
    2026-10-16)".
  - **README crash bullet:** say that if images-downloader wrote no manifest for this run (it
    crashed before its final write, or no scan staged) and no legacy `run_manifest.json` is
    present (the no-run-id rule keeps it that way; readers still honour it under
    `allow_legacy=True`), predict exits 1 and spends its retries
    holding a GPU slot, citing the predictor template's comment. Also say that a `Failed` Workflow
    still doesn't imply nothing was written. Do not repeat "scoped by whatever … an earlier run
    left".
  - **Predictor template, comments only:** drop the present-tense "accumulates scan_keys across
    every run" in the `ARGO_WORKFLOW_NAME` env comment. Mark the "scoped by whatever
    predictions/run_manifest.json an earlier run left" clause as pre-a9.
  - **`runai_run_pipeline.sh` header comment:** environments differ by label, stage root and Secret
    (bloom#988); link the runbook's guard by path. The comment is plain text; the script's behavior
    is unchanged.
  - **`per-batch-pipeline` spec:** the MODIFIED delta (in this change) rewords the rationale
    paragraph. It takes effect at archive and its existing scenario is unchanged.

  Validate:
  - 3.1 PASSes; green;
  - `bash -n runai_run_pipeline.sh`;
  - the parsed-YAML check in 4.2 also covers the predictor template.

## 4. The unlink procedure (cluster-access-docs Req 2: The unlink procedure names its side effect)

- [x] 4.1 Add the assertion: `comment_block(TRAIT_TEMPLATE, "Rollback (updated 2026-10-04, #119)")`
  matches `unlink\(\)[^.]*candidate`.

  Validate (red): `FAIL  trait-extractor rollback comment names unlink's candidate side effect:
  got False, expected True`.
- [x] 4.2 Edit comments only. Keep the substring `Rollback (updated 2026-10-04, #119)` unchanged.
  - **Trait-extractor comment:** the cards are linked (2026-10-05). The order follows the roadmap's
    2026-10-05 entry:
    1. `unlink()`, which also drops `candidate` and `latest`;
    2. re-publish `candidate`;
    3. confirm with a fresh `wandb.Api()` that `list_cards()` = 8;
    4. re-pin.
  - **Predictor comment:** change "once … are linked" to "now that … are linked (2026-10-05)" and
    point at the trait-extractor comment.

  Validate:
  - 4.1 PASSes; green, including `check_manifests.py`;
  - `/lint` is clean;
  - for each changed template, `uv run --no-project --with pyyaml python -c "import yaml,subprocess
    as s,sys; f=sys.argv[1]; a=yaml.safe_load(s.check_output(['git','show','origin/main:'+f]));
    b=yaml.safe_load(open(f)); sys.exit(a!=b)" <file>` exits 0. That means a comment-only change,
    and no deploy (the drift check compares parsed YAML).

## 5. The runbook and its inbound links (cluster-access-docs Req 1)

- [x] 5.1 Add the assertions, against `ops = text_or_empty(OPS)`:
  - **Exists:** `OPS` exists.
  - **Headings:** `re.findall(r"^## (.+)$", ops, re.M)` equals the six headings, in order.
  - **"Before any change to the cluster":** contains `.status.phase`,
    `scripts/check_cluster_drift.sh`, `runai_run_pipeline.sh`, `SRP_PREDICT_CONTAINER_DIGEST` and
    `SRT_TRAITS_CONTAINER_DIGEST` (one check each).
  - **"Switching production off is not a pause":** contains `CYL_PIPELINE_TRIGGER_ENABLED` and
    `](../cluster-identities.md`.
  - **"Rollback":** contains `](../../sleap-roots-trait-extractor-template.yaml`,
    `](../../sleap-roots-predictor-template.yaml` and
    `](../../sleap-roots-images-downloader-template.yaml`.
  - **"Preconditions nothing enforces":** contains `](../../sleap-roots-pipeline-semaphores.yaml`.
  - **"When a run fails":** contains `WORKFLOWS_K8S_TTL_SECONDS`,
    `](../../.claude/commands/ci-debug.md` and `](../../sleap-roots-exit-gate-template.yaml`.
  - **"Standing operator rules":** contains `bloom_cyl_pipeline/prod`.
  - **Issue links:** the issues in `[63, 106, 109, 127, 128, 137]` not linked as
    `github.com/talmolab/sleap-roots-pipeline/issues/N(?!\d)`, want `[]`. The same for
    `[857, 859, 939, 1042]` under `Salk-Harnessing-Plants-Initiative/bloom/issues/N(?!\d)`.
  - **Links resolve:** relative link targets that don't exist (`#` fragment stripped, http
    skipped), want `[]`.
  - **No pins:** `re.findall(r"\bsha-[0-9a-f]{7,}|sha256:[0-9a-f]{6,}|(?<![\w/#.-])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}(?!\w)", ops)`, want `[]`.
  - **OPS joins the claim-wide scans:** append `OPS` to the section-1 a4_poc list and the
    section-2 startup list.
  - **README callout:** the raw lines from the one beginning `> ⚠️ This namespace is shared by
    Bloom's staging` through the last consecutive line starting with `>` contain
    `](docs/bloom-integration/operations.md`.
  - **README Troubleshooting:** the section-3 slice contains
    `](docs/bloom-integration/operations.md`.
  - **Roadmap hard constraint:** `between(roadmap_n, "**Shared templates, production live",
    "- **Argo stays**")` matches `\]\((\./)?operations\.md` and does not contain `Running or Pending`.
  - **Roadmap item 10:** `between(roadmap_n, "10. **Production hardening backlog**", "**Closed
    since the 2026-10-01 review**")` matches the same link and does not contain
    `No prod runbook exists`.
  - **cluster-identities:** contains `](bloom-integration/operations.md`.
  - **tdd.md:** `between(tdd, "## Live acceptance tests", "\n## ")` contains
    `](../../docs/bloom-integration/operations.md` and does not contain `Running or Pending`.
  - **project.md:** `between(project_n, "**Live acceptance**", "(A4, later)")` contains
    `](../docs/bloom-integration/operations.md` and does not contain `Running or Pending`.

  Validate (red), before the page exists, expecting:
  - `FAIL  operations.md exists: got False, expected True`;
  - a FAIL for each content check;
  - `FAIL` on each inbound link;
  - `roadmap hard constraint: no idle restatement: got True, expected False`;
  - `roadmap item 10: no 'No prod runbook exists': got True, expected False`.

  The no-pin and links-resolve checks pass vacuously on an empty page; 5.3 proves them. List every
  FAIL line in the commit body.
- [x] 5.2 Write `operations.md` per design.md:
  - the guard procedure in full;
  - every other rule as one or two sentences plus a link to its owner;
  - Rollback starts at the trait-extractor `Rollback` comment ("it states which rollback needs
    predict first") rather than copying the layers;
  - the TTL window as "at most";
  - no pins.

  Add the inbound links:
  - README callout and Troubleshooting;
  - roadmap hard constraint: keep the reach fact, link the page, and move "The idle check is
    point-in-time…" to the page;
  - roadmap item 10: rewrite as "the runbook: operations.md";
  - `cluster-identities.md` "Related";
  - `tdd.md` step 3: link the page for the whole guard and keep only "re-run the same observation";
  - `openspec/project.md` "Live acceptance": link the page.

  Also update `.claude/commands/test.md`'s table of files the suites read. Add `operations.md`,
  `tdd.md`, the 2026-09-21 design spec, the two templates,
  `runai_run_pipeline.sh` and the roadmap (missing already).

  Before committing, re-check every factual claim on the page against its source or live state,
  read-only: `gh issue view`, template comments, Bloom `origin/main` (cite functions, not line
  numbers). Record the date in the commit body.

  Validate: 5.1 PASSes; green.
- [x] 5.3 Prove the content checks are not vacuous. Stage the page first (`git add`). Then run one
  mutation at a time; each run must FAIL on exactly the targeted check:
  - delete each checked phrase or link **only inside its own section**;
  - swap two whole sections (heading and body);
  - add `sha-5b709d0`, then `sha256:ba5693fc1dec`, then `e45b6bf`;
  - add a link to a missing file;
  - add "the shared `a4_poc` trees" and "fails pod startup";
  - remove only the README callout's link.

  Then revert each and confirm with `git diff --quiet -- docs/bloom-integration/operations.md
  README.md`.

  Validate: record the mutation → FAIL table in the section-5 commit body.

## 6. Gate (commit `docs(openspec): record the pre-merge sweep for add-production-runbook (#132)`)

- [x] 6.1 Run the suite: all PASS.
- [x] 6.2 Run `/lint` (two template comments changed): clean.
- [x] 6.3 Run `uvx codespell` over every changed file.
- [x] 6.4 Run `openspec validate add-production-runbook --strict` and
  `openspec validate --all --strict`.
- [x] 6.5 Check the merge base: `git fetch origin && git merge-base --is-ancestor origin/main HEAD`.
- [x] 6.6 Check the `*.yaml` scope: `git diff --name-only origin/main...HEAD -- '*.yaml'` lists only
  the trait-extractor and predictor templates, and 4.2's parsed-YAML check passes for both.
- [x] 6.7 Run `/docs-review`.

## 7. After merge (not in this PR)

- [ ] 7.1 A post-merge PR adds the roadmap status-log entry, archives the change, and applies both
  deltas to the specs (#129 pattern).
- [ ] 7.2 After #136 merges, refresh the dashboard's #132 card.
- [ ] 7.3 `tdd.md`, `ci-debug.md` and `test.md` are rendered from the vault's canonical command templates.
  Port the repo-specific edits there, or confirm the re-render keeps them.

## 8. PR #140 review fixes (in this PR, before merge)

- [x] 8.1 Assert the guard's safety properties and the review's claim fixes. Red before the edits:
  the guard property list (9 missing), the launcher header, the Rollback layer restatement,
  "predict writes the legacy manifest" (SKILL, page, roadmap), bloom#1042's fix, and the
  predictor and trait-extractor rollback comments. Also widen the idle-restatement check from the
  literal "Running or Pending", and normalise the cumulative-manifest scan.
- [x] 8.2 Make the fixes:
  - **Guard:** `srp_idle` is a function under `pipefail`. It fails closed on the list and on the
    filter, matches by `templateRef`, counts a Workflow with no phase as in flight, and chains as
    `srp_idle && argo template update`.
  - **Steps 3 and 6:** a safe rollback copy and a read-back command.
  - **Launcher:** "not a deploy path", on the page and in its header.
  - **Rollback:** links the trait-extractor comment instead of restating the layers; bloomctl
    goes to the last target.
  - **Claims:** predict and traits forward manifests and don't write them; bloom#1042's fix is
    #1048; the predictor comment scopes predict-first to bloom#971 phase 1; the trait comment adds
    step (0).
  - **Spec, design, roadmap item 10:** wording aligned.
- [x] 8.3 Mutation-prove the new checks. Each mutation produced exactly one FAIL on its target,
  after two vacuous checks found this way were tightened.
- [ ] 8.4 Retire the below-a9-floor rollback (owner decision (b), 2026-10-22), red first (next
  commit).
