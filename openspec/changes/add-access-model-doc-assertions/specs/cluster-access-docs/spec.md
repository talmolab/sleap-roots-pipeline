# cluster-access-docs

## ADDED Requirements

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
no VPN and no credentials, SHALL exit non-zero when any assertion fails, and SHALL be invoked by
the same entry point that runs the manifest assertions, so that a documentation regression is
caught by the same command as a manifest regression.

#### Scenario: Assertions run offline

- **WHEN** `python scripts/check_docs.py` is run from the repository root with no `KUBECONFIG` set
  and no network access
- **THEN** it completes without contacting the cluster
- **AND** exits `0` when all assertions hold and `1` when any fails

#### Scenario: The shared entry point runs both suites

- **WHEN** `scripts/lint_manifests.sh` is run
- **THEN** it runs the documentation assertions as well as the manifest assertions
- **AND** a failure in either causes a non-zero exit
