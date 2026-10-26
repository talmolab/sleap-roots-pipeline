# cluster-access-docs Specification

## Purpose
TBD - created by archiving change add-access-model-doc-assertions. Update Purpose after archive.
## Requirements
### Requirement: Access-model documentation distinguishes the two authentication planes

The repository's operator documentation SHALL state that Kubernetes RBAC and RunAI identity are
separate authentication planes, and SHALL state per tool which plane(s) it requires: `argo` and
`kubectl` require only the shared `argo-user` kubeconfig; the `runai` CLI requires that kubeconfig
*and* an active per-person RunAI SSO session; the RunAI console requires only SSO. Documentation
SHALL NOT state that per-person RunAI console access does not exist, and SHALL NOT describe `runai`
as authenticating by kubeconfig alone. Because these are facts about cluster configuration that
cannot be derived from anything in this repository, each such claim SHALL carry its provenance —
who confirmed it and when.

#### Scenario: The retracted claims do not reappear

- **WHEN** `scripts/check_docs.py` scans `docs/cluster-identities.md`, `README.md` and
  `.claude/skills/runai/SKILL.md`
- **THEN** no file asserts that there is no per-person RunAI console access
- **AND** no file describes the `runai` CLI as needing only a kubeconfig
- **AND** the assertion fails if any of those strings reappears

#### Scenario: Every tool's auth requirements are stated consistently

- **WHEN** the auth-plane table in `docs/cluster-identities.md` is compared with `README.md`'s tool
  table and identity sentence
- **THEN** both state that `runai` requires the kubeconfig **and** SSO
- **AND** both state that `argo` and `kubectl` do not require SSO
- **AND** neither assigns `runai` exactly one credential

#### Scenario: The auth-plane claims carry provenance

- **WHEN** the section stating the two auth planes is read
- **THEN** it names who confirmed the facts and on what date

### Requirement: Documented cluster inventory matches the manifests in the repository

Documented counts and lists SHALL match the manifests present in the repository. Where the access
documentation states a count or a list of WorkflowTemplates, priority classes, or `hostPath`
volumes, that statement SHALL be checked by an executable assertion rather than by prose review,
and SHALL fail the check when a manifest changes without the documentation changing with it.
Documentation SHALL NOT assert
that the live cluster matches this repository, because that is a mutable property of a shared
namespace which no assertion in this repository can hold true; it MAY record a dated observation
and SHALL point at the drift-checking script instead.

#### Scenario: Documented template count matches the repository

- **WHEN** `scripts/check_docs.py` counts `sleap-roots-*-template.yaml` files that the launcher
  registers
- **THEN** every count stated in `docs/cluster-identities.md` matches that number
- **AND** the assertion fails if a template is added or removed without the documentation changing

#### Scenario: Documented priority classes match the templates

- **WHEN** the documentation names a `priorityClassName` for a stage
- **THEN** that value equals the value in the corresponding template manifest

#### Scenario: No standing claim that the cluster matches the repository

- **WHEN** the documentation refers to the registered templates in the live namespace
- **THEN** it does not assert present-tense parity with this repository
- **AND** it points the reader at `scripts/check_cluster_drift.sh`

### Requirement: Documentation assertions run with the repository's other checks

The documentation assertions SHALL be executable from the repository root with no cluster access,
no VPN and no credentials, SHALL exit non-zero when any assertion fails, and SHALL be invoked by a
shared entry point that also runs the manifest assertions, so that a documentation regression is
caught by the same command as a manifest regression. That entry point SHALL NOT require `argo` to
be installed, since neither assertion suite needs it.

#### Scenario: Assertions run offline

- **WHEN** `python scripts/check_docs.py` is run from the repository root with no `KUBECONFIG` set
  and no network access
- **THEN** it completes without contacting the cluster
- **AND** exits `0` when all assertions hold and `1` when any fails

#### Scenario: The shared entry point runs both suites

- **WHEN** `scripts/check_all.sh` is run
- **THEN** it runs the documentation assertions as well as the manifest assertions
- **AND** a failure in either causes a non-zero exit
- **AND** it succeeds on a machine with no `argo` binary installed

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
change that reaches both environments: an `argo template update` or `create`, or a registry
`production` link. The page, README and the launcher's header SHALL say that
`runai_run_pipeline.sh` is not a deploy path. The semaphore retune is owned by the ConfigMap's header and is outside
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
- **AND** the guard is a function that fails closed when the Workflow list or its filter fails,
  counts a Workflow with no phase as in flight, and matches hand-submitted runs by `templateRef`
- **AND** inside the `srp_idle` function it runs under `pipefail`, fails closed when the list or the
  filter fails, counts a Workflow with no phase as in flight, and lists DAG, steps and
  `workflowTemplateRef` template references
- **AND** it checks for an up-to-date clean `main`, chains `srp_idle && argo template update`, copies
  each template in one loop that fails closed, gives the digest read-back command, and separates an
  emergency restore from a planned re-pin PR
- **AND** a registry link takes steps 2 and 8
- **AND** the page, README's callout and "Run the Pipeline" section, and the launcher's header each
  say `runai_run_pipeline.sh` is not a deploy path, and the launcher's header has no batch
  template-update recipe
- **AND** the roadmap's hard constraint, `tdd.md` and `openspec/project.md` don't restate the idle
  condition as a phase list (Running and Pending, in either order), `.status.phase` or "no phase"

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
- **AND** it states bloom#1042's fix (Bloom PRs #1045 and #1048) as deployed, linking both PRs

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
- **Manifest writers.** Only bloomctl creates a run manifest. predict and traits forward one that is
  present, and otherwise run unscoped.
- **Run manifests.** Since contracts a9, run manifests are per run. The legacy `run_manifest.json`
  no longer accumulates scan keys.
- **Environments.** They differ by label, stage root and Secret, not by label alone.
- **The a9 floor.** A bloomctl rollback below the a9 floor (reversing row 6), and the predict
  re-pin below its floor tied to it, are retired (owner, 2026-10-22). Text that offered them
  carries a "retired 2026-10-22" marker.

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

#### Scenario: The retired below-floor rollback is marked wherever it was offered

- **WHEN** `scripts/check_docs.py` reads the roadmap's step-6 restore note and "Deliberate" bullet,
  the images-downloader header's restore line and the predictor's below-floor sentence
- **THEN** each carries the "retired 2026-10-22" marker

#### Scenario: Rollback sends the operator to the owners, in scope

- **WHEN** `scripts/check_docs.py` reads the page's "Rollback" section and the rollback comments
- **THEN** the page's step 2 is a pointer to the trait-extractor comment, not a list of layers
- **AND** bloomctl goes to the last `Rollback target:`, reverting in the reverse of the deploy order
- **AND** the page states the below-a9-floor rollback as retired on 2026-10-22
- **AND** the predictor comment scopes predict-first to undoing bloom#971 phase 1, and the
  trait-extractor comment starts with step (0), the idle check
- **AND** the roadmap's frontier item 3 rollback bullet is scoped the same way

#### Scenario: Manifest writers are stated as observed

- **WHEN** `scripts/check_docs.py` scans runai SKILL, the runbook, the roadmap and the 2026-09-21
  design spec
- **THEN** none says predict or traits writes, creates or starts a legacy run manifest

#### Scenario: The unlink procedure names its side effect

- **WHEN** `scripts/check_docs.py` reads the trait-extractor template's rollback comment
- **THEN** a sentence that names `unlink()` also names `candidate`, and one names `latest`
- **AND** the roadmap's frontier item 3 names `latest` too

