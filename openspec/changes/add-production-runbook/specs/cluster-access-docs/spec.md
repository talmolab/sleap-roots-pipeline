## ADDED Requirements

### Requirement: A production runbook exists, is reachable, and defers to its sources

The repository SHALL have one operator page for running the pipeline in production,
`docs/bloom-integration/operations.md`. It SHALL have these six `##` sections, in this order:

1. "Before any change to the cluster"
2. "Switching production off is not a pause"
3. "Rollback"
4. "Preconditions nothing enforces"
5. "When a run fails"
6. "Standing operator rules"

**The guard procedure.** The page SHALL be the canonical statement of the guard procedure for a
change that reaches both environments: an `argo template update`, `runai_run_pipeline.sh`, or a
registry `production` link. The semaphore retune is owned by the ConfigMap's header and is outside
the guard. Three places SHALL link to the page for the idle guard and SHALL NOT restate the idle
condition:

- the roadmap's "Shared templates, production live" hard constraint;
- `.claude/commands/tdd.md`'s "Live acceptance tests" section;
- `openspec/project.md`'s "Live acceptance" bullet.

Dated status-log entries and completed frontier items are history and are exempt.

**Other rules.** For every other rule, the page SHALL link to the source that owns it rather than
restate that source's detail. The owners are a template's comment, the semaphore ConfigMap header,
a roadmap section, `docs/cluster-identities.md`, `.claude/commands/ci-debug.md`, or an issue.

**No pins.** The page SHALL NOT contain an image tag, image digest or commit SHA. It SHALL tell the
operator to re-derive live pins with `scripts/check_cluster_drift.sh`, consistent with this
capability's rule against parity claims.

**Inbound links.** The README, the roadmap and `docs/cluster-identities.md` SHALL link to the page.

#### Scenario: The page exists and is reachable

- **WHEN** `scripts/check_docs.py` runs
- **THEN** `docs/bloom-integration/operations.md` exists
- **AND** the README links to it from its shared-namespace callout and from its Troubleshooting
  section
- **AND** the roadmap links to it from the "Shared templates, production live" hard constraint
  and from the "Production hardening backlog" frontier item
- **AND** that frontier item no longer says "No prod runbook exists"
- **AND** `docs/cluster-identities.md` links to it

#### Scenario: The six sections appear in order

- **WHEN** `scripts/check_docs.py` lists the page's `##` headings
- **THEN** they are exactly the six headings above, in that order

#### Scenario: The guard procedure is canonical on the page

- **WHEN** `scripts/check_docs.py` reads the page's "Before any change to the cluster" section
- **THEN** it names `.status.phase`, `scripts/check_cluster_drift.sh`, `runai_run_pipeline.sh`,
  `SRP_PREDICT_CONTAINER_DIGEST` and `SRT_TRAITS_CONTAINER_DIGEST`
- **AND** the roadmap's hard constraint, `tdd.md`'s "Live acceptance tests" section and
  `openspec/project.md`'s "Live acceptance" bullet each link to the page
- **AND** the roadmap's hard constraint no longer contains "Running or Pending"

#### Scenario: Switching production off is not presented as a pause

- **WHEN** `scripts/check_docs.py` reads the page's second section
- **THEN** it names `CYL_PIPELINE_TRIGGER_ENABLED`
- **AND** it contains a markdown link to `../cluster-identities.md`

#### Scenario: Rollback and failure sections link their owners

- **WHEN** `scripts/check_docs.py` reads the page's sections
- **THEN** the "Rollback" section links the trait-extractor, predictor and images-downloader
  template files
- **AND** the "Preconditions nothing enforces" section links `sleap-roots-pipeline-semaphores.yaml`
- **AND** the "When a run fails" section names `WORKFLOWS_K8S_TTL_SECONDS` and links
  `.claude/commands/ci-debug.md` and `sleap-roots-exit-gate-template.yaml`
- **AND** every relative link on the page resolves to an existing file

#### Scenario: The issues the rules depend on are linked

- **WHEN** `scripts/check_docs.py` scans the page
- **THEN** it links this repo's issues #63, #106, #109, #127, #128 and #137
- **AND** it links Bloom issues #857, #859, #939 and #1042

#### Scenario: No pin, digest or commit SHA is hard-coded

- **WHEN** `scripts/check_docs.py` scans the page for `sha-<hex>`, `sha256:<hex>` and bare hex
  commit SHAs of 7 or more characters
- **THEN** it finds none

### Requirement: Operator documentation does not contradict observed operating facts

Operator text SHALL NOT contradict the facts below, whether it is a document, command file, skill,
script header or template comment in this repository. None of them SHALL restrict to one
environment a rule that applies to both.

- **Missing `hostPath`.** A pod whose `hostPath` directory is missing stays `Pending` and the
  Workflow hangs. It does not fail pod startup.
- **Retention.** A Bloom-dispatched Workflow is deleted at most `WORKFLOWS_K8S_TTL_SECONDS` after
  it completes, and its pods and logs may go sooner. A hand-submitted Workflow carries no TTL.
- **Workflow access.** `argo-user` can `get`, `list` and `watch` Workflows.
- **No-run-id runs.** A run with no run id must not be pointed at either environment's shared stage
  tree: `a4_poc` for staging, `bloom_cyl_pipeline/prod` for prod.
- **Unlinking.** Unlinking a registry card also removes its `candidate` and `latest` aliases.
- **Run manifests.** Since contracts a9, run manifests are per run. The legacy `run_manifest.json`
  no longer accumulates scan keys.
- **Environments.** They differ by label, stage root and Secret, not by label alone.

#### Scenario: The no-run-id rule covers both shared trees

- **WHEN** `scripts/check_docs.py` reads the roadmap's operator rule against pointing a no-run-id
  run at a shared tree
- **THEN** the rule names both `a4_poc` and `bloom_cyl_pipeline/prod`
- **AND** the roadmap's "Deliberate" pre-a9 rollback bullet names `bloom_cyl_pipeline/prod`
- **AND** no document, including the runbook, limits the rule to "the shared `a4_poc` trees"
- **AND** runai SKILL §6 links the rule

#### Scenario: A missing hostPath is described as Pending

- **WHEN** `scripts/check_docs.py` scans `openspec/project.md`, `README.md`,
  `.claude/commands/ci-debug.md` and the runbook
- **THEN** none says that a missing `hostPath` fails pod startup, in either word order
- **AND** `ci-debug.md`'s Pending row does not recommend `retryStrategy`

#### Scenario: Failure evidence, access and manifests are stated as observed

- **WHEN** `scripts/check_docs.py` reads the docs below
- **THEN** `docs/cluster-identities.md`'s pod-log paragraph, `ci-debug.md`'s section A and README's
  Troubleshooting section each name `WORKFLOWS_K8S_TTL_SECONDS` or link #137
- **AND** the "Can" cell of `cluster-identities.md`'s `argo-user` row lists
  `` `get`/`list`/`watch workflows` ``
- **AND** neither README nor the predictor template describes the legacy `run_manifest.json` as
  accumulating across every run
- **AND** `runai_run_pipeline.sh` does not say the environments are distinguished only by a label

#### Scenario: The unlink procedure names its side effect

- **WHEN** `scripts/check_docs.py` reads the trait-extractor template's rollback comment
- **THEN** a sentence that names `unlink()` also names `candidate`
