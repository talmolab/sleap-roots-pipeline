# Cluster Identities & Namespace Drift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the launcher's stale namespace default, delete the dropped models-downloader template, and document the three cluster identities so a new Bloom-side developer can get access without reverse-engineering roadmap log entries.

**Architecture:** Three independent phases. Phase 0 is secret hygiene (`.gitignore` patterns and a TLS-flag fix), done first because it is cheap and hardens the repo before new docs land. Phase 1 is an orchestration change (one shell default, one file deletion) and carries an OpenSpec delta because the launcher's namespace is not currently specced. Phase 2 is documentation only — a new `docs/cluster-identities.md`, a README namespace sweep, and repair of two stale headers that actively mislead readers. The phases are separately committable and a reviewer can split them into two PRs.

**Tech Stack:** Argo Workflows YAML, bash launcher, OpenSpec CLI, markdown. No application code, no unit-test harness.

**Spec:** This plan's "Findings" section below serves as the spec. Every finding cites the file and line it was verified against; no design exploration was required because each item is a factual repair. Source material: `openspec/specs/per-batch-pipeline/spec.md`, `docs/bloom-integration/roadmap.md`, `openspec/changes/archive/2026-08-12-wire-bloom-workflow-sa/`.

## Global Constraints

- Target namespace for this pipeline is `runai-busch-lab` (project `busch-lab`). `runai-talmo-lab` is still live on the cluster but is **not** this pipeline's target since 2026-08-13.
- Verification in this repo means `argo lint`, a grep-based manifest/script field assertion, or a real cluster submit — **not** `pytest` or a build step.
- Do NOT write manifest/script changes in Phase 1 until the OpenSpec proposal is approved by Elizabeth.
- Never state an RBAC fact in documentation that has not been verified live. Where a fact cannot be verified, say so explicitly and say why.
- **This repo is PUBLIC** (`gh repo view talmolab/sleap-roots-pipeline` → `"isPrivate": false`). Document credential *names* and *paths* only — env var names, kubeconfig filenames, secret object names. Never a token, CA cert, kubeconfig body, password, or bearer value, not even truncated or as an example. Use `<your-token>`-style placeholders.
- Do not add *new* cluster IPs, hostnames, or internal endpoints to tracked files. The ones already committed stay (see F8 item 2) — this rule is about not widening the footprint, not about placeholders.
- Keep cluster (`*.yaml`) and local (`local-WSL2-*.yaml`) variants in sync. The local variants do not reference any ServiceAccount and are out of scope here.
- Commit messages end with: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## Findings (the spec)

### F1 — Launcher namespace default is wrong (live defect)

`runai_run_pipeline.sh:23` sets `NAMESPACE="runai-talmo-lab"`, while the Workflow it submits declares `metadata.namespace: runai-busch-lab` (`sleap-roots-pipeline.yaml:28`). Running the launcher as-is registers templates into, and submits against, the wrong namespace.

**Confirmed safe to change:** Bloom's dispatch path is unaffected. `salk-bloom` contains zero references to `runai_run_pipeline.sh` (verified by grep across `*.py`/`*.yml`/`*.yaml`/`*.md`), and `services/workflows/k8s_client.py:48-49` resolves the namespace from `WORKFLOWS_K8S_NAMESPACE` (default `runai-busch-lab`), then overwrites `body["metadata"]["namespace"]` at line 227 so the body always matches the URL segment. The launcher is operator-only.

**Decision (Elizabeth, 2026-09-15):** flip the default to `runai-busch-lab`, keep an env-var override.

### F2 — models-downloader template is dead

`models-downloader-template.yaml` carries a stale `project: talmo-lab` label (line 6) and its stage was dropped from the DAG. The current DAG is `images-downloader` → `predictor` → `trait-extractor` → `write-back`, and `openspec/specs/per-batch-pipeline/spec.md:191-198` specs the launcher as registering exactly those four.

**Decision (Elizabeth, 2026-09-15):** delete the file. Git history retains it.

### F3 — README namespace drift

`README.md` references `runai-talmo-lab` on 15 lines (46, 57, 74, 82, 166-169, 175, 192-194, 200-202) plus `project: talmo-lab` at line 250 — 20 `talmo` occurrences in total. All are copy-pasteable commands that would target the wrong namespace.

### F4 — openspec/project.md namespace drift

`openspec/project.md:34` and `:143` both describe the stack as using the `runai-talmo-lab` namespace.

### F5 — ServiceAccount manifest header is stale

`bloom-pipeline-serviceaccount.yaml`'s header block still reads `STOPGAP STATUS (2026-08-03): the cluster admin has not applied this manifest`, and frames the busch-lab variant as a guess with "unconfirmed which project Bloom submissions should target". Both are false: Bryan provisioned `bloom-pipeline` in `runai-busch-lab` on 2026-08-07 (`docs/bloom-integration/roadmap.md:913`) and busch-lab is the confirmed target.

### F6 — RBAC investigation doc's framing actively misleads

`docs/superpowers/specs/2026-08-03-busch-lab-rbac-investigation-design.md` describes `argo-user` as "Elizabeth's local ServiceAccount kubeconfig" / "Elizabeth's own", and as cluster-wide in scope. Both were superseded on 2026-08-12 when the cluster admin created a **namespace-scoped, shared project** `argo-user` for `runai-busch-lab` (`roadmap.md:1002-1006`). It is a point-in-time investigation doc, so it gets a superseded-by banner rather than a rewrite.

### F7 — No single place documents the three identities

Identity facts are scattered across a manifest's comments, an archived OpenSpec change, a superseded design doc, and dated roadmap prose. `README.md` contains zero occurrences of `serviceaccount`, `kubeconfig`, `credential`, or `identity`.

The verified facts to document:

| Identity | Who authenticates as it | Can | Cannot | Credential |
|---|---|---|---|---|
| `bloom-pipeline` | Bloom's backend, from outside the cluster (`bloom-dev`) | `create`/`get`/`list`/`watch` on `argoproj.io/workflows`; `get`/`list` on `workflowtemplates`; **`get`/`list`/`watch` on `pods` and `get pods/log`** | `create`/`update workflowtemplates`; `delete`/`update workflows`; `create pods/exec`; `create workflowtaskresults`; `secrets`, `configmaps`, `nodes`; anything outside its namespace | `~/.kube/kubeconfig-bloom-pipeline-busch-lab.yaml`; deployed as `WORKFLOWS_K8S_TOKEN`/`_CA_CERT`/`_API_URL` |
| `bloom-workflow` | Each DAG step's own pod (set via `spec.serviceAccountName`) | `workflowtaskresults` `create`/`patch` | not used for submission; nobody holds a kubeconfig for it | none — set on the Workflow, Argo does the rest |
| `argo-user` (busch-lab, namespace-scoped) | Operators, shared project identity | `get pods`, `get pods/log`, `create pods/exec`; `create`+`update workflowtemplates`; `create`+`delete workflows` | `get serviceaccounts`, `get secrets`, `create workflowtaskresults` | `~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml` |

**⚠️ The applied `bloom-pipeline` does not match this repo's drafted manifest.** Verified
2026-09-15 by running `kubectl auth can-i` under its *own* kubeconfig, not inferred from
`bloom-pipeline-serviceaccount.yaml`. The manifest's comment says `pods` / `pods/log` were "NOT
requested for v1 (intentionally omitted, least-privilege)" — but the identity the cluster admin
actually applied **can** `get`/`list`/`watch` pods and `get pods/log`. It cannot `create pods/exec`.
Everything else in the manifest held exactly: workflows `create`/`get`/`list`/`watch` yes,
`delete`/`update` no; workflowtemplates `get`/`list` yes, `create`/`update` no; secrets,
configmaps, nodes, serviceaccounts all no.

⚠️ **Corrected 2026-09-16 — the `pods/log` and `pods/exec` cells in both tables above are wrong.** They were measured with `kubectl auth can-i get pods/log`, where everything after the slash is parsed as a resource *name*, not a subresource — so the query asked "can I get a pod **named** `log`" and merely mirrored bare `pods` access. Re-measured with `--subresource=`: `argo-user` **cannot** read logs and **cannot** exec (it answers `yes` to both slash forms only because it can `create pods` and `get pods` outright); `bloom-pipeline` **can** read logs and cannot exec. Nobody can exec. Every other cell in these tables held on re-measurement. See `docs/cluster-identities.md` and `openspec/changes/add-access-model-doc-assertions/`.

The manifest describes what was *requested*; the cluster holds what was *granted*. The doc must
state the granted set and say where it came from, and `bloom-pipeline-serviceaccount.yaml`'s
"intentionally omitted" comment needs a correction noting it no longer describes reality
(fold into Task 6).

One caveat that must appear in the doc:

1. **`bloom-workflow`'s RBAC still cannot be read from our side** — re-confirmed live 2026-09-15,
   not inherited from the archived note: `kubectl auth can-i get serviceaccounts -n runai-busch-lab`
   returns **no** under `argo-user`, as does `get secrets`. Its existence was confirmed only
   indirectly (pod admission succeeded, no `workflowtaskresults.argoproj.io is forbidden` error),
   and the `workflowtaskresults create/patch` verb comes from the cluster admin's description.
   State it that way in the doc; do not assert it as read from the cluster.

   Corroborating evidence worth including: `argo-user` itself returns **no** for
   `create workflowtaskresults.argoproj.io`. That is exactly why `bloom-workflow` has to exist —
   the identity that submits a Workflow cannot report its steps' results.

**`argo-user`'s access is now fully verified** (2026-09-15, live `kubectl auth can-i` against
`runai-busch-lab`), so the second caveat is resolved and must not be carried into the doc:

| Permission | Result |
|---|---|
| `get pods` | yes |
| `get pods/log` | yes |
| `create pods/exec` | yes |
| `create workflowtemplates.argoproj.io` | yes |
| `update workflowtemplates.argoproj.io` | yes |
| `create workflows.argoproj.io` | yes |
| `delete workflows.argoproj.io` | yes |
| `get serviceaccounts` | no |
| `get secrets` | no |
| `create workflowtaskresults.argoproj.io` | no |

This also definitively closes the time-conflict noted during the sweep: `argo-user` **does** have
`create`/`update` on `workflowtemplates` in `runai-busch-lab` now. The contrary record in
`openspec/changes/archive/2026-08-12-wire-bloom-workflow-sa/tasks.md` step 4.2 (issue #40) applied
to the *original* cluster-wide `argo-user`, and was resolved by the namespace-scoped replacement.

Also worth documenting: because `k8s_client.py` overwrites `metadata.namespace`, that field in `sleap-roots-pipeline.yaml` only affects hand-run `argo submit`, not Bloom dispatch.

**Decision (Elizabeth, 2026-09-15):** reference doc **plus** an onboarding section aimed at a new Bloom-side developer, replacing the README's stale access section.

### F8 — Secret hygiene: no leaked credentials, but real gaps

A sweep of all tracked files found **no** private keys, certificates, JWTs, bearer tokens, or `certificate-authority-data`/`client-key-data` blobs. `.env` is ignored. Nothing needs revocation. Three gaps remain:

1. **`.gitignore` does not cover the credential filenames this program actually produces.** It has `secrets.yaml`, `service-account.json`, `.kube/`, `.kubectl/`, `.env`. It does **not** cover `*kubeconfig*`, `bloom-staging-k8s-secrets.txt` (a real file holding five staging values, per `roadmap.md:923`), `credentials*.txt` (matching `~/.bloom/credentials.pipeline-staging.txt`), `*.pem`, `*.crt`, `*.key`, or `.env.*` variants. A stray copy into the repo root would be committed silently.
2. **The cluster API endpoint is published**, along with `gpu-master:8888`, in `README.md`, `bloom-pipeline-serviceaccount.yaml:166`, `runai_run_pipeline.sh`, and four `roadmap.md` lines. **Decision (Elizabeth, 2026-09-15): leave both as-is.** They are internal-only, unresolvable off the Salk VPN, and already in public git history, so removal is cosmetic rather than remediation — and placeholders would make the README less usable. The forward-looking rule in Global Constraints (do not add *new* endpoints) still applies.
3. **`README.md:41-46` teaches `--insecure-skip-tls-verify`** as the documented token check. In a public repo that is a bad-practice example, independent of any leak.

Two lower-severity items, both since decided (see Task 0 Step 7): a colleague's personal `@salk.edu` address appeared in a tracked doc — **removed**, along with the name in the same eviction note — and the service-account identifier `bloom-pipeline-workflows@salk.edu` appears 4 times, **deliberately retained** since it is an account name rather than a credential and the credential docs are useless without it. Neither was ever a secret; both are identifiers in a public repo. Note that removing the personal address is forward-looking only: it remains in git history, so this is hygiene for future readers, not remediation.

### F9 — No CLI setup instructions distinguishing the two tools

`README.md:17-64` mixes `runai`, `kubectl`, and `argo` setup without saying which tool needs what, or which identity each uses. It links the `argo` CLI docs but not the Run:AI CLI docs, does not mention `kubectl` as a requirement despite documenting `kubectl` commands, does not mention the Salk VPN requirement, and does not mention that this program's cluster commands run in **WSL** with an explicit `KUBECONFIG`, not in Windows PowerShell.

What each tool actually needs:

| Tool | Auth it uses | Needed for | Identity |
|---|---|---|---|
| `runai` | interactive SSO (`runai login remote-browser`) | workspace submit/list/logs/exec — the interactive, ad-hoc path | the operator's own SSO login |
| `argo` | `ARGO_TOKEN` + `ARGO_SERVER` (Argo Server mode), **or** `KUBECONFIG` (Kubernetes mode) | template registration, workflow submit, `argo logs` — the production path | `argo-user` in Kubernetes mode |
| `kubectl` | `KUBECONFIG` | pod inspection, `auth can-i`, describing failures | `argo-user` |

---

## File Structure

| File | Responsibility |
|---|---|
| `.gitignore` | Add the credential filename patterns this program produces (Task 0) |
| `openspec/changes/fix-launcher-namespace/` | Phase 1 OpenSpec proposal, tasks, and spec delta |
| `runai_run_pipeline.sh` | Modify line 23 default + the stale kubeconfig comment at lines 6-13 |
| `models-downloader-template.yaml` | Delete |
| `docs/cluster-identities.md` | **New.** Identity reference table + caveats + onboarding path |
| `README.md` | Namespace sweep + access-section pointer (Task 4); CLI setup rewrite (Task 4A); endpoint + TLS-flag repair (Task 0) |
| `openspec/project.md` | Namespace correction, 2 lines |
| `bloom-pipeline-serviceaccount.yaml` | Header repair only — no RBAC changes |
| `docs/superpowers/specs/2026-08-03-busch-lab-rbac-investigation-design.md` | Superseded-by banner at top |

---

## Prerequisite: branch

- [ ] **Step 1: Confirm you are not on main and create the branch**

```bash
cd /c/repos/sleap-roots-pipeline
git branch --show-current   # expect: main
git checkout -b fix-namespace-drift-and-document-identities
git branch --show-current   # expect: fix-namespace-drift-and-document-identities
```

---

# Phase 0 — Secret hygiene

Do this first. It is cheap, independent of everything else, and it hardens the repo *before* Phase 2 writes new documentation that references credential paths.

### Task 0: Harden .gitignore and repair published infrastructure detail

**Files:**
- Modify: `.gitignore`
- Modify: `README.md:41-46` (the token-check block)
- Modify: `bloom-pipeline-serviceaccount.yaml:166` (comment only)

**Interfaces:**
- Consumes: finding F8.
- Produces: the `scripts/`-free scan command reused in the Pre-merge sweep, and a repo where a stray kubeconfig cannot be committed silently.

- [ ] **Step 1: Confirm nothing is currently leaked**

```bash
git ls-files -z | xargs -0 grep -lniE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|BEGIN CERTIFICATE|eyJ[A-Za-z0-9_-]{20,}|bearer [A-Za-z0-9._-]{20,}|client-key-data|certificate-authority-data' 2>/dev/null
```
Expected: no output. If this prints a file, **stop and tell Elizabeth immediately** — a committed credential in a public repo needs rotating, not a `.gitignore` line.

- [ ] **Step 2: Add the missing ignore patterns**

Append to `.gitignore`, replacing the existing `# Ignore Kubernetes secrets and service account tokens` block:

```gitignore
# Kubernetes / cluster credentials — this repo is PUBLIC, keep these out.
# Covers the real filenames this program produces: kubeconfig-bloom-pipeline-busch-lab.yaml,
# kubeconfig-runai-busch-lab-argo-user.yaml, bloom-staging-k8s-secrets.txt,
# credentials.pipeline-staging.txt
secrets.yaml
service-account.json
*kubeconfig*
*-secrets.txt
*secrets*.txt
credentials*
*.pem
*.crt
*.key
.env
.env.*
!.env.example
```

- [ ] **Step 3: Verify the patterns actually match the real filenames**

```bash
for f in kubeconfig-bloom-pipeline-busch-lab.yaml \
         kubeconfig-runai-busch-lab-argo-user.yaml \
         bloom-staging-k8s-secrets.txt \
         credentials.pipeline-staging.txt \
         ca.crt cluster.pem; do
  printf "%-45s " "$f"; git check-ignore -q "$f" && echo IGNORED || echo "NOT IGNORED"
done
```
Expected: all six `IGNORED`. `git check-ignore` works on paths that do not exist, so this is safe to run without creating anything.

- [ ] **Step 4: Verify no tracked file became ignored**

```bash
git ls-files | git check-ignore --no-index --stdin 2>/dev/null
```
Expected: no output. A hit means a pattern is too broad and shadows a real tracked file — narrow it.

**`--no-index` is required.** Without it `git check-ignore` skips tracked files entirely and this
guard is inert: verified 2026-09-15 with a throwaway `*.md` pattern, which returned **0 hits
without** the flag and **52 hits with** it. Do not drop it.

Verified 2026-09-15: with the Step 2 patterns, zero tracked files match — the shadowing risk is
currently nil. Keep the guard anyway, since the patterns may be widened later.

- [ ] **Step 5: Fix the insecure TLS flag (endpoints stay as-is)**

**Decision (Elizabeth, 2026-09-15): redact neither endpoint.** The cluster API IP and
`gpu-master:8888` both stay literal in tracked files. Both are internal-only, unresolvable off the
Salk VPN, and already in public git history — removing them buys nothing real while making the
README less copy-pasteable. Do **not** replace them with placeholders.

The TLS flag is a separate issue and is still worth fixing. In `README.md`, keep the existing
`--server=` and `--namespace=` lines (correcting the namespace to `runai-busch-lab` per Task 4),
and replace `--insecure-skip-tls-verify` with CA verification:

````markdown
### 🔑 Token check

```bash
kubectl --server=https://<the endpoint already in this README> \
  --certificate-authority=/path/to/ca.crt \
  --token="<your-token>" \
  --namespace=runai-busch-lab \
  get pods
```

Prefer `--certificate-authority` over `--insecure-skip-tls-verify`; skipping verification
disables the protection that makes a bearer token safe to send. If you need the endpoint for a
different cluster or context, read it from your own kubeconfig rather than copying it — it
travels with the credential:

```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```
````

Leave `bloom-pipeline-serviceaccount.yaml:166` unchanged.

- [ ] **Step 6: Verify only the TLS flag changed**

```bash
grep -n 'insecure-skip-tls-verify' README.md
```
Expected: no output.

```bash
git diff --stat README.md bloom-pipeline-serviceaccount.yaml
```
Expected: `README.md` only. The ServiceAccount manifest must be untouched by this task (Task 6 edits its header separately).

- [ ] **Step 7: Personal-name removal — already applied 2026-09-15**

Both decided and done ahead of execution; nothing to do here beyond confirming they held:

```bash
git ls-files -z | xargs -0 grep -niE '<colleague-surname>' 2>/dev/null
```
Expected: no output (substitute the actual surname when running it — don't hard-code a personal
identifier into this tracked file). A colleague's email and the eviction-context name were removed from
`docs/superpowers/plans/2026-08-07-handoff-bloom-credential-and-busch-lab.md`, and that file's
colleague-commentary guardrail was reworded to state the rule without naming anyone. The research
attribution at `docs/bloom-integration/roadmap.md:447` is deliberately retained — it cites whose
project is out of scope, the same way the adjacent bullet cites `egao28's Metcalf project`.

`bloom-pipeline-workflows@salk.edu` is deliberately retained (Elizabeth, 2026-09-15): it is a
service-account identifier, not a credential, and the credential docs are useless without it.

- [ ] **Step 8: Commit**

```bash
git add .gitignore README.md bloom-pipeline-serviceaccount.yaml
git commit -F- <<'MSG'
chore: harden gitignore for cluster credentials, verify TLS in docs

This repo is public. .gitignore covered secrets.yaml and .kube/ but not
the credential filenames this program actually produces (kubeconfig-*,
*-secrets.txt, credentials*). Adds those patterns.

Also replaces the documented --insecure-skip-tls-verify token check
with one that verifies the CA. Cluster endpoints are deliberately left
published: internal-only, unresolvable off-VPN, and already in git
history. No credential was ever committed - a full sweep of tracked
files found no keys, certs, or tokens.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

# Phase 1 — Orchestration fixes (OpenSpec-gated)

### Task 1: OpenSpec proposal for the launcher namespace

**Files:**
- Create: `openspec/changes/fix-launcher-namespace/proposal.md`
- Create: `openspec/changes/fix-launcher-namespace/tasks.md`
- Create: `openspec/changes/fix-launcher-namespace/specs/per-batch-pipeline/spec.md`

**Interfaces:**
- Consumes: findings F1 and F2 above.
- Produces: change-id `fix-launcher-namespace`, referenced by Task 2's commit and the eventual PR body.

- [ ] **Step 1: Scaffold the change via the OpenSpec command**

Invoke `/openspec:proposal` with change-id `fix-launcher-namespace`. Ground it with F1 and F2 verbatim, including the salk-bloom evidence (that `k8s_client.py:48-49` and `:227` make the launcher operator-only), so a reviewer does not have to re-derive that the change is safe.

- [ ] **Step 2: Write the spec delta**

> **⚠️ SUPERSEDED — do not execute this step as written (note added 2026-09-16).** The delta text
> below specifies a `NAMESPACE` environment-variable override and a "Launcher namespace is
> overridable" scenario. **The override cannot work and was removed before merge.** `argo submit
> -n <ns>` does not redirect a submission — the manifest's `metadata.namespace` wins (verified:
> `argo submit --server-dry-run -n runai-talmo-lab -o json` → `metadata.namespace =
> runai-busch-lab`), and `argo-user` has no create rights in `runai-talmo-lab` anyway. All an
> override could do is publish the templates into a different project than the one the Workflow
> runs in.
>
> What actually shipped is a plain literal `NAMESPACE="runai-busch-lab"`, a requirement stating the
> value SHALL NOT be overridable, and a scenario asserting it is a literal rather than a parameter
> expansion. See the archived change at
> `openspec/changes/archive/2026-09-16-fix-launcher-namespace/` and the live requirement in
> `openspec/specs/per-batch-pipeline/spec.md`, not the draft below.
>
> Left in place rather than rewritten: this is a record of what was planned, and the gap between it
> and what shipped is the useful part. Flagged because the text below is an *instruction to an
> executor* — re-running it verbatim would re-introduce the broken override.

The existing requirement at `openspec/specs/per-batch-pipeline/spec.md:191` ("Launcher registers all four templates") covers only the `TEMPLATES` list. Add a MODIFIED delta extending it with a namespace assertion. The delta file must contain:

```markdown
## MODIFIED Requirements

### Requirement: Launcher registers all four templates

The cluster launcher (`runai_run_pipeline.sh`) SHALL register the `images-downloader`, `predictor`,
`trait-extractor`, and `write-back` templates. It SHALL default its target namespace to
`runai-busch-lab`, overridable via a `NAMESPACE` environment variable, so that the namespace it
registers and submits into matches `sleap-roots-pipeline.yaml`'s own `metadata.namespace`.

#### Scenario: Launcher's TEMPLATES list contains all four stage templates

- **WHEN** `runai_run_pipeline.sh` is inspected
- **THEN** its registered `TEMPLATES` list contains all four template files: the images-downloader,
  predictor, trait-extractor, and write-back templates

#### Scenario: Launcher defaults to the busch-lab namespace

- **WHEN** `runai_run_pipeline.sh` is run with no `NAMESPACE` set in the environment
- **THEN** its effective namespace is `runai-busch-lab`
- **AND** that value equals `sleap-roots-pipeline.yaml`'s `metadata.namespace`

#### Scenario: Launcher namespace is overridable

- **WHEN** `runai_run_pipeline.sh` is run with `NAMESPACE=runai-talmo-lab` set
- **THEN** its effective namespace is `runai-talmo-lab`
```

- [ ] **Step 3: Validate strictly**

Run: `openspec validate fix-launcher-namespace --strict`
Expected: `valid`. Fix every reported issue before continuing.

- [ ] **Step 4: Commit the proposal**

```bash
git add openspec/changes/fix-launcher-namespace
git commit -F- <<'MSG'
docs(openspec): propose launcher namespace default fix

Covers the runai_run_pipeline.sh talmo-lab default (F1) and the dead
models-downloader template (F2).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

- [ ] **Step 5: STOP — get Elizabeth's approval**

Present the change-id, the one-line summary, and the affected capability (`per-batch-pipeline`, MODIFIED). Do not proceed to Task 2 until she approves.

---

### Task 2: Fix the launcher default and delete the dead template

**Files:**
- Modify: `runai_run_pipeline.sh:23` (the default) and `runai_run_pipeline.sh:6-13` (stale comment block)
- Delete: `models-downloader-template.yaml`

**Interfaces:**
- Consumes: approval from Task 1 Step 5.
- Produces: a launcher whose namespace matches the manifest; used by the Phase 2 README rewrite, which documents the new override.

- [ ] **Step 1: Assert the current (broken) state**

```bash
grep -n 'NAMESPACE=' runai_run_pipeline.sh
```
Expected: `23:NAMESPACE="runai-talmo-lab"` — confirms you are fixing what the plan describes.

- [ ] **Step 2: Flip the default to busch-lab with an override**

Replace line 23's `NAMESPACE="runai-talmo-lab"` with:

```bash
# Namespace for the GPU cluster. Must match sleap-roots-pipeline.yaml's
# metadata.namespace. Override for a one-off submit into another project:
#   NAMESPACE=runai-talmo-lab ./runai_run_pipeline.sh
NAMESPACE="${NAMESPACE:-runai-busch-lab}"
```

- [ ] **Step 3: Fix the stale kubeconfig comment block**

Lines 6-13 tell the reader to `export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml` and run every `argo template update` against `-n runai-talmo-lab`. Update the kubeconfig filename to `~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml` and every `-n runai-talmo-lab` in that block to `-n runai-busch-lab`.

- [ ] **Step 4: Verify the script's namespace default is correct**

```bash
grep -n 'runai-talmo-lab' runai_run_pipeline.sh
```
Expected: exactly one hit — the override example on the new comment line added in Step 2.

```bash
grep -n 'NAMESPACE="${NAMESPACE:-runai-busch-lab}"' runai_run_pipeline.sh
```
Expected: one hit. This asserts the literal line is present.

The script cannot be executed to observe its effective namespace — it registers templates and
submits a real Workflow, so there is no dry-run path. A field assertion is the honest limit here;
do not substitute a standalone `bash -c` echo of the same idiom and call it a test of the script.

- [ ] **Step 5: Confirm launcher and manifest agree**

```bash
grep -m1 '^  namespace:' sleap-roots-pipeline.yaml | awk '{print $2}'
```
Expected: `runai-busch-lab` — the same value Step 4 printed.

- [ ] **Step 6: Delete the dead template and confirm nothing references it**

```bash
git rm models-downloader-template.yaml
grep -rn 'models-downloader-template' --include='*.sh' --include='*.yaml' --include='*.md' . \
  | grep -v '.worktrees' | grep -v 'docs/superpowers' | grep -v 'openspec/changes/archive'
```
Expected: no output. If the launcher's `TEMPLATES` list or the README folder-structure block still names it, remove those references before committing.

- [ ] **Step 7: Lint every remaining manifest**

**`argo` lives in WSL only** — `/usr/local/bin/argo`, v3.6.5, verified 2026-09-15. It is **not**
installed on Windows (no `scoop`/`choco` shim, nothing under `Program Files`), so `argo` is not on
PATH in Git Bash or PowerShell and the lint loop must run through WSL. Note the repo path
translates to `/mnt/c/repos/sleap-roots-pipeline`. Working invocation:

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; cd /mnt/c/repos/sleap-roots-pipeline && argo lint --offline sleap-roots-pipeline.yaml'   # offline: see note below
```

**Prefer non-offline lint — `sleap-roots-pipeline.yaml` passes it.** Verified 2026-09-15: with the
`argo-user` kubeconfig and Salk VPN, `argo lint sleap-roots-pipeline.yaml` returns
`✔ no linting errors found!` (exit 0). That is the authoritative gate:

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \
export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \
cd /mnt/c/repos/sleap-roots-pipeline && argo lint sleap-roots-pipeline.yaml'
```

`argo lint --offline` on that same file exits **1** with
`couldn't find workflow template "sleap-roots-images-downloader-template" in namespace
"runai-busch-lab"`. That is a tool artifact, not a defect: the DAG references its four stages by
`templateRef` to separately-registered WorkflowTemplates, and offline lint has no cluster to
resolve them against. **Correction (2026-09-15, after review):** offline lint *does* index sibling files — it matches
`templateRef` on **(namespace, name)**. The Workflow declares `namespace: runai-busch-lab` while
the templates declare none, so the lookup searches a namespace nothing is indexed under. Strip
`metadata.namespace` from a **temp copy** and all five lint clean with no cluster:
`T=$(mktemp -d); cp sleap-roots-*.yaml "$T/"; sed -i '/^  namespace: runai-busch-lab$/d' "$T/sleap-roots-pipeline.yaml"; argo lint --offline "$T"/sleap-roots-*.yaml`.
Prefer that as the gate — it works without VPN. Never strip the line from the real file. Earlier records in this
repo (including `openspec/changes/archive/2026-08-12-wire-bloom-workflow-sa/tasks.md` step 2.1)
describe the offline failure as the expected result without noting that the online lint passes
clean — don't inherit that framing.

So: if VPN is available, use non-offline lint and expect a clean pass. If not, offline lint is a
fallback whose one known error must be read as expected, and which must not be wired into
anything treating non-zero exit as failure. The four stage templates lint clean either way.

If `argo` cannot be reached at all, record that in `tasks.md` rather than marking the step done,
and rely on Step 4/5's field assertions plus a real cluster submit instead. Do not claim a lint
passed that never ran.

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \
export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \
cd /mnt/c/repos/sleap-roots-pipeline; \
for f in sleap-roots-pipeline.yaml sleap-roots-images-downloader-template.yaml \
         sleap-roots-predictor-template.yaml sleap-roots-trait-extractor-template.yaml \
         sleap-roots-write-back-template.yaml; do
  echo "--- $f"; argo lint "$f"; done'
```
`KUBECONFIG` must be set so `templateRef`s resolve against the registered templates — that is the whole difference between this passing and the offline artifact. Expected: **all five clean**, including `sleap-roots-pipeline.yaml` (verified 2026-09-15). Any error is a real failure.

Without VPN, fall back to `--offline` and expect exactly one error on `sleap-roots-pipeline.yaml` — the `templateRef` artifact described above. Any *other* error is real.

- [ ] **Step 8: Tick the OpenSpec tasks and commit**

Mark the matching items `- [x]` in `openspec/changes/fix-launcher-namespace/tasks.md`, then:

```bash
git add runai_run_pipeline.sh openspec/changes/fix-launcher-namespace/tasks.md
git commit -F- <<'MSG'
fix: default launcher namespace to runai-busch-lab, drop dead template

runai_run_pipeline.sh defaulted to runai-talmo-lab while the Workflow it
submits declares metadata.namespace: runai-busch-lab, so a hand-run
launcher registered templates into the wrong namespace. Bloom's dispatch
path is unaffected - it never invokes this script and overwrites
metadata.namespace from WORKFLOWS_K8S_NAMESPACE.

Also deletes models-downloader-template.yaml: that stage is not in the
four-task DAG and the file carried a stale project: talmo-lab label.

OpenSpec: fix-launcher-namespace

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

# Phase 2 — Documentation

### Task 3: Write docs/cluster-identities.md

**Files:**
- Create: `docs/cluster-identities.md`

**Interfaces:**
- Consumes: finding F7's table and both caveats, verbatim.
- Produces: the canonical identity reference. Tasks 4 and 6 link to it at this exact path.

- [ ] **Step 1: Write the file**

The document has five sections, in this order:

1. **`## The three identities`** — the F7 table, reproduced exactly, including the Cannot column. The Cannot column is the most useful part of the page: it is what stops someone building against an identity that cannot do what they need.

2. **`## Submit vs. report back`** — explain the split, because it produces a confusing failure. `bloom-pipeline` submits the Workflow object from outside the cluster; `bloom-workflow` is what each step's pod runs as so it can report results to Argo. A Workflow that submits cleanly will have *every* step fail with `workflowtaskresults.argoproj.io is forbidden` if `spec.serviceAccountName: bloom-workflow` is missing. Cite `sleap-roots-pipeline.yaml:39` as the single line that sets it, and note that none of the four stage templates override `serviceAccountName`, so that one value covers all steps.

3. **`## What is not verified`** — both F7 caveats, stated plainly:
   - `bloom-workflow`'s Role has never been read. `argo-user` is forbidden from `kubectl get serviceaccount` (`openspec/changes/archive/2026-08-12-wire-bloom-workflow-sa/tasks.md`, step 3.1). Existence was inferred from successful pod admission plus the absence of a `workflowtaskresults` error. The `create`/`patch` verbs come from the cluster admin's description.
   - `argo-user`'s `pods`/`pods/log` access is unrecorded. Task 5 fills this in.

4. **`## Getting access (new Bloom-side developer)`** — the onboarding path:
   - If Bloom dispatches your workflows, you need no new credential. Reuse `services/workflows/k8s_client.py` (`build_workflow_body` / `submit_workflow` / `get_workflow_status`); the token is already deployed as `WORKFLOWS_K8S_TOKEN`/`_CA_CERT`/`_API_URL` for staging and prod.
   - Your WorkflowTemplates must be registered in the namespace first. `bloom-pipeline` cannot do this — it has `get`/`list` on `workflowtemplates` only. Use the shared project `argo-user` kubeconfig.
   - Any Argo DAG you submit needs `spec.serviceAccountName: bloom-workflow` or every step fails on results reporting.
   - You will not get pod logs through the Bloom path: `bloom-pipeline` has no `pods`/`pods/log` and the status poller only surfaces Workflow phases. For a new ServiceAccount with log access, copy `bloom-pipeline-serviceaccount.yaml` and ask the cluster admin. ⚠️ **Corrected 2026-09-15:** the applied `bloom-pipeline` identity **does** have `get`/`list`/`watch pods` and `get pods/log` — verified live under its own kubeconfig, and documented in `docs/cluster-identities.md`. The manifest's "intentionally omitted" comment describes the request, not the grant. Do not send anyone to the cluster admin for a capability they already hold.
   - ⚠️ **Corrected 2026-09-15:** ~~There is no per-person RunAI console access; work is driven from the `argo`/`runai` CLI against a kubeconfig.~~ Both halves are wrong. Per-person RunAI console access exists via SSO, and `runai` needs that SSO session *in addition to* the shared kubeconfig, while `argo`/`kubectl` need only the kubeconfig. This was an unsourced assertion that shipped into `docs/cluster-identities.md`; see `openspec/changes/add-access-model-doc-assertions/`.
   - The cluster API endpoint is not published in this repo. Read it from your own kubeconfig with `kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'` — it travels with the credential. The Argo Server endpoint (`gpu-master:8888`) is in `runai_run_pipeline.sh`. Neither is reachable off the Salk VPN.

5. **`## Namespace facts that bite`** —
   - `runai-busch-lab` is shared by Bloom staging *and* production, disambiguated only by an env label stamped on each submitted Workflow. An `argo template update` therefore affects both environments' future dispatches. A production dispatch deployment is live in that namespace.
   - Deserved GPU quota is 2. Set `priorityClassName` explicitly unless you have a reason not to — `interactive-preemptible` for CPU stages. ⚠️ **Corrected 2026-09-16 (PR #60's review):** this line said an unset value "lands at `very-high` (150), which is non-preemptible and can evict others' running sessions". That was never verified and is very likely wrong — pods observed with no class resolved to priority **0** (lowest tier), and `priorityclasses` is Forbidden to our credentials. The risk of omitting the field is starvation, not evicting others.
   - `metadata.namespace` in `sleap-roots-pipeline.yaml` only affects hand-run `argo submit`. Bloom's `k8s_client.py` overwrites it from `WORKFLOWS_K8S_NAMESPACE` (line 227) so the body matches the URL segment.

- [ ] **Step 2: Verify every claim in the file traces to a citation**

```bash
grep -c 'roadmap.md\|tasks.md\|spec.md\|k8s_client.py\|serviceaccount.yaml\|sleap-roots-pipeline.yaml' docs/cluster-identities.md
```
Expected: at least `8`. Any RBAC or access claim without a file citation is a plan violation — the whole point of this document is that the previous scattered version got `argo-user`'s ownership wrong.

- [ ] **Step 3: Verify no unverified claim is stated as fact**

```bash
grep -n 'bloom-workflow' docs/cluster-identities.md
```
Read every hit. Each statement about its RBAC must be hedged and attributed to the cluster admin's description, not asserted as read from the cluster.

- [ ] **Step 4: Commit**

```bash
git add docs/cluster-identities.md
git commit -F- <<'MSG'
docs: add cluster identities reference and onboarding guide

Consolidates identity facts previously scattered across a manifest's
comments, an archived OpenSpec change, a superseded design doc, and
dated roadmap entries. Marks explicitly which RBAC facts are verified
and which are only inferred.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 4: README namespace sweep and access section

**Files:**
- Modify: `README.md` — lines 46, 57, 74, 82, 166-169, 175, 192-194, 200-202, 250, plus the `## 🛠️ Setup and Cluster Access` section at line 27

**Interfaces:**
- Consumes: `docs/cluster-identities.md` from Task 3 (linked, not duplicated); the `NAMESPACE` override from Task 2.
- Produces: nothing downstream.

- [ ] **Step 1: Assert the current state**

```bash
grep -c 'runai-talmo-lab' README.md
```
Expected: **`14` if Task 0 has already run**, `15` if not. Task 0 Step 5 rewrote the token-check block at line 46, which removed one `runai-talmo-lab` occurrence. Record the number you actually get; Step 4 checks the end state. A count outside {14, 15} means the file drifted from this plan — re-read it before editing.

- [ ] **Step 2: Replace every namespace reference**

Change all `runai-talmo-lab` → `runai-busch-lab` and `project: talmo-lab` → `project: busch-lab` (line 250). Update the heading at line 82 to ``## 🚀 Running on the GPU Cluster (`runai-busch-lab`)``, and the folder-structure comment at line 74 to say `(runai-busch-lab)`. Remove the `models-downloader-template.yaml` entry from the folder-structure block if present.

Add one sentence under the line-82 heading:

> `runai-talmo-lab` remains live on the cluster but is no longer this pipeline's target (changed 2026-08-13). Override with `NAMESPACE=runai-talmo-lab` if you genuinely need it.

- [ ] **Step 3: Do NOT touch the access section here**

`## 🛠️ Setup and Cluster Access` is rewritten wholesale by **Task 4A**, including the identity pointer and the `docs/cluster-identities.md` link. Editing it here would be clobbered. This task changes namespace strings only — if a namespace string falls inside that section, Task 4A's replacement text already has the corrected value, so leave it.

- [ ] **Step 4: Verify the sweep is complete**

```bash
grep -n 'talmo' README.md
```
Expected: only the one intentional sentence from Step 2 mentioning that talmo-lab is no longer the target.

- [ ] **Step 5: Confirm Task 4A's precondition**

Task 4A links `docs/cluster-identities.md`, so Task 3 must have landed first:

```bash
test -f docs/cluster-identities.md && echo OK || echo "run Task 3 before Task 4A"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -F- <<'MSG'
docs(readme): correct namespace to runai-busch-lab

Every argo/kubectl command in the README targeted runai-talmo-lab,
which has not been this pipeline's namespace since 2026-08-13.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 4A: RunAI and Argo CLI setup instructions

**Files:**
- Modify: `README.md:17-64` — the `## 🧰 Requirements` and `## 🛠️ Setup and Cluster Access` sections

**Interfaces:**
- Consumes: finding F9's tool table; Task 0's repaired token-check block (do not re-introduce the endpoint or the insecure flag); `docs/cluster-identities.md` from Task 3.
- Produces: nothing downstream.

- [ ] **Step 1: Rewrite the Requirements section**

Replace `## 🧰 Requirements` (lines 17-24) with an explicit three-tool list. Each entry says what the tool is for and what it authenticates with:

````markdown
## 🧰 Requirements

Three separate CLIs, with three different auth mechanisms. You do not need all three for
every task — see the table below.

| Tool | Install | Auth | Use it for |
|---|---|---|---|
| `runai` | Run:AI CLI v2 (see Run:AI docs link below) | interactive SSO: `runai login remote-browser` | interactive/ad-hoc work: `runai workspace submit`/`logs`/`exec` |
| `argo` | [Argo Workflows CLI](https://argo-workflows.readthedocs.io/en/latest/cli/argo/) | `ARGO_TOKEN` + `ARGO_SERVER`, **or** `KUBECONFIG` (Kubernetes mode) | the production path: template registration, `argo submit`, `argo logs` |
| `kubectl` | [kubectl install docs](https://kubernetes.io/docs/tasks/tools/) | `KUBECONFIG` | pod inspection, `kubectl auth can-i`, diagnosing failures |

Also required:

- **Salk VPN** (or on-campus network) — the cluster API and Argo Server are not reachable from
  outside.
- **WSL**, not Windows PowerShell. Every cluster command in this repo assumes a POSIX shell with
  an explicit `KUBECONFIG` export. In Git Bash, prefix cluster-path commands with
  `MSYS_NO_PATHCONV=1` so `/hpi/...` is not rewritten into a Windows path.
- A GPU-capable Kubernetes cluster and storage available via `hostPath`.
- (Optional, local testing only) Docker Desktop with WSL2 integration — CPU-only, see the local
  testing section.

**Which identity does each tool use?** `runai` uses your own SSO login; `argo` and `kubectl` use
the shared project `argo-user` kubeconfig. Bloom's backend uses a third identity you do not hold.
See [Cluster identities](docs/cluster-identities.md).
````

- [ ] **Step 2: Add the Run:AI CLI docs link — verify it resolves first**

The README currently links no Run:AI documentation. Run:AI was acquired by NVIDIA, so older `run.ai` documentation URLs may redirect or 404. **Do not paste a URL you have not opened.** Check the candidates and use whichever resolves:

```bash
for u in https://docs.run.ai/ \
         https://run-ai-docs.nvidia.com/ \
         https://docs.nvidia.com/run-ai/; do
  printf "%-40s " "$u"; curl -s -o /dev/null -w '%{http_code}\n' -L "$u"
done
```
Verified 2026-09-15: **all three returned `200`.** Prefer `https://run-ai-docs.nvidia.com/` as
the post-acquisition canonical host, but re-run the check before committing — a host that
resolved today can be retired. If none return `200`, write `Run:AI CLI v2 — see your cluster
admin for the current documentation URL` rather than a dead link, and say so in the PR body.

- [ ] **Step 3: Rewrite the Setup and Cluster Access section**

Keep the working mechanics, fix what is stale, and make the WSL pattern explicit:

````markdown
## 🛠️ Setup and Cluster Access

> **Which identity am I using?** This section covers the operator path (`argo-user`). Bloom's
> backend submits as a different identity, and pipeline step pods run as a third. See
> [Cluster identities](docs/cluster-identities.md) before wiring anything new — picking the wrong
> one produces confusing failures.

### ✅ Run:AI login (interactive path)

```bash
runai login remote-browser
runai whoami
```

### ⚙️ Argo CLI — Kubernetes mode (what this repo's launcher uses)

Point `KUBECONFIG` at the `argo-user` kubeconfig. No `ARGO_TOKEN` is needed in this mode:

```bash
export KUBECONFIG=~/.kube/kubeconfig-runai-busch-lab-argo-user.yaml
kubectl config get-contexts
argo list -n runai-busch-lab
```

### ⚙️ Argo CLI — Argo Server mode

Use this only if `gpu-master:8888` is reachable from your machine. Never commit a token value:

```bash
export ARGO_SERVER=gpu-master:8888
export ARGO_HTTP1=true
export ARGO_SECURE=false
export ARGO_NAMESPACE=runai-busch-lab
export ARGO_TOKEN="Bearer <your-token>"
```
````

- [ ] **Step 4: Verify no secret or endpoint was reintroduced**

```bash
grep -nE 'insecure-skip-tls-verify|eyJ[A-Za-z0-9_-]{20,}' README.md
```
Expected: no output. Task 0 removed all three; this step confirms the rewrite did not bring them back.

- [ ] **Step 5: Verify every documentation link resolves — and fix two pre-existing dead ones**

```bash
grep -ohE 'https?://[^ )"]+' README.md | sed 's/[.,]$//' | sort -u \
  | grep -vE '^https://([0-9]{1,3}[.]){3}[0-9]{1,3}' | while read -r u; do
  printf "%-72s " "$u"; curl -s -o /dev/null -m 12 -w '%{http_code}\n' -L "$u"
done
```

The `grep -v` excludes the cluster API endpoint — it appears inside a `kubectl --server=` command,
is not a documentation link, and returns `000` off-VPN. Expected: `200` for every remaining URL.

**Two links were already 404 before this work** (verified 2026-09-15). Fix them here, since this
task is rewriting the README's links anyway:

- `https://argo-workflows.readthedocs.io/en/stable/cli/` → **404**. Replace with
  `https://argo-workflows.readthedocs.io/en/latest/cli/argo/` (verified `200`). This is the same
  URL the old Requirements section linked, so Step 1's table uses the replacement.
- `https://argo-workflows.readthedocs.io/en/latest/retry-failed-steps/` → **404**. Find the
  current page under `https://argo-workflows.readthedocs.io/en/stable/` (verified `200`) or drop
  the link and keep the prose.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -F- <<'MSG'
docs(readme): separate runai/argo/kubectl setup and state what each needs

The Requirements and Setup sections mixed three CLIs with three
different auth mechanisms without saying which tool needs what, listed
no Run:AI documentation, omitted kubectl despite documenting kubectl
commands, and did not mention the VPN or WSL requirements.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 5: Re-verify argo-user's RBAC before the doc ships

**Files:**
- Modify: `docs/cluster-identities.md` — only if the re-run disagrees with F7's recorded table

**Interfaces:**
- Consumes: Task 3's document, which already contains F7's verified `argo-user` row.
- Produces: confirmation that the recorded RBAC still holds, or a corrected row.

**Already done once — this task is a re-confirmation, not a discovery.** The full sweep ran live
against `runai-busch-lab` on 2026-09-15 and its results are in F7. `kubectl` **is** installed, in
two places: `/home/elizabeth/bin/kubectl` in WSL (note: `$HOME/bin` is **not** on the non-login
WSL PATH, so export it) and Docker Desktop's v1.34.1 on the Windows side, already on the Git Bash
PATH. An earlier claim in this plan that `kubectl` was missing was wrong — it checked
`$HOME/.local/bin` but not `$HOME/bin`.

Re-run it anyway before the doc ships: RBAC is cluster-admin-mutable and the doc's whole value is
that its table is true. Requires Salk VPN.

- [ ] **Step 1: Re-run the permission sweep**

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; export KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; for r in "get pods" "get pods/log" "create pods/exec"          "create workflowtemplates.argoproj.io" "update workflowtemplates.argoproj.io"          "create workflows.argoproj.io" "delete workflows.argoproj.io"          "get serviceaccounts" "get secrets" "create workflowtaskresults.argoproj.io"; do   printf "  %-44s " "$r"; timeout 25 kubectl auth can-i $r -n runai-busch-lab 2>/dev/null     | grep -E "^(yes|no)" || echo "?"; done'
```

**The `2>/dev/null | grep -E "^(yes|no)"` is required.** `kubectl` emits a deprecation warning
("Use tokens from the TokenRequest API...") on stderr that interleaves with the answers — a bare
`| head -1` captures the warning instead of the verdict and silently produces garbage. This was
observed for real on the first run.

Expected, matching F7:

| Permission | Result |
|---|---|
| `get pods` | yes |
| `get pods/log` | yes |
| `create pods/exec` | yes |
| `create workflowtemplates.argoproj.io` | yes |
| `update workflowtemplates.argoproj.io` | yes |
| `create workflows.argoproj.io` | yes |
| `delete workflows.argoproj.io` | yes |
| `get serviceaccounts` | no |
| `get secrets` | no |
| `create workflowtaskresults.argoproj.io` | no |

- [ ] **Step 2: If anything disagrees, the doc is wrong — fix the doc, not the table**

Update `docs/cluster-identities.md`'s `argo-user` row to what the cluster actually returned, note
the new verification date, and say what changed. A drift here is itself worth recording: it means
someone altered the project's RBAC since 2026-09-15.

- [ ] **Step 3: If the sweep cannot run (no VPN), say so and do not block**

Leave the doc as-is with its 2026-09-15 verification date, and note in the PR body that the table
was not re-confirmed at merge time. The date on the table is what makes that honest.

- [ ] **Step 4: Commit only if something changed**

```bash
git diff --quiet docs/cluster-identities.md && echo "no change - nothing to commit" || git add docs/cluster-identities.md && git commit -F- <<'MSG'
docs: re-confirm argo-user RBAC against the live cluster

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 6: Repair the two stale headers and project.md

**Files:**
- Modify: `bloom-pipeline-serviceaccount.yaml` — header comment block (lines 1-30)
- Modify: `docs/superpowers/specs/2026-08-03-busch-lab-rbac-investigation-design.md` — add a banner at the top
- Modify: `openspec/project.md:34` and `:143`

**Interfaces:**
- Consumes: findings F4, F5, F6.
- Produces: nothing downstream. Deliberately last so it cannot block the useful work.

- [ ] **Step 1: Repair the ServiceAccount manifest header**

Replace the `STOPGAP STATUS (2026-08-03)` paragraph with a current-state note: the manifest was applied by the cluster admin on 2026-08-07 in `runai-busch-lab`; `bloom-pipeline` is live and is the identity Bloom's backend authenticates as; `runai-busch-lab` is this pipeline's confirmed target and the talmo-lab variant is retained for reference only. Keep the token-generation instructions unchanged — they are still correct. **Do not change any RBAC rule**; this is a comment-only edit.

- [ ] **Step 2: Verify no RBAC was touched**

```bash
git diff HEAD -- bloom-pipeline-serviceaccount.yaml | grep '^[+-]' | grep -v '^[+-][+-]' | grep -v '^[+-][[:space:]]*#'
```
Expected: no output. Every changed line must be a comment.

**`git diff HEAD`, not bare `git diff`** — bare `git diff` shows unstaged changes only, so once
the file is staged this guard silently passes on any edit, including an RBAC change.

- [ ] **Step 3: Banner the superseded investigation doc**

Insert immediately below its title:

```markdown
> **⚠️ Superseded in part (2026-08-12).** This document describes `argo-user` as Elizabeth's own
> ServiceAccount with cluster-wide Workflow access. Both statements were true when written and are
> no longer: the cluster admin created a **namespace-scoped, shared project `argo-user`** for
> `runai-busch-lab` on 2026-08-12 (`docs/bloom-integration/roadmap.md:1002-1006`). The dedicated
> `bloom-pipeline` ServiceAccount this document treats as blocked was applied 2026-08-07. For
> current identity facts see [Cluster identities](../../cluster-identities.md). The investigation's
> method and findings are retained as a point-in-time record.
```

- [ ] **Step 4: Fix project.md**

Change `runai-talmo-lab` → `runai-busch-lab` at lines 34 and 143.

```bash
grep -c 'runai-talmo-lab' openspec/project.md
```
Expected: `0`

- [ ] **Step 5: Verify the banner's relative link resolves**

From `docs/superpowers/specs/`, `../../cluster-identities.md` resolves to `docs/cluster-identities.md`:

```bash
test -f docs/superpowers/specs/../../cluster-identities.md && echo OK
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add bloom-pipeline-serviceaccount.yaml openspec/project.md \
        docs/superpowers/specs/2026-08-03-busch-lab-rbac-investigation-design.md
git commit -F- <<'MSG'
docs: retire stale stopgap framing in SA manifest and RBAC design doc

The ServiceAccount manifest still claimed the cluster admin had not
applied it (applied 2026-08-07). The RBAC investigation doc described
argo-user as a personal, cluster-wide identity; it was replaced by a
namespace-scoped shared project identity on 2026-08-12. Comment- and
prose-only; no RBAC rules changed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Pre-merge sweep

- [ ] **Step 1: Namespace drift is gone from every tracked file**

```bash
git ls-files -z | xargs -0 grep -ln 'runai-talmo-lab' 2>/dev/null
```
Expected: only `README.md` (the one intentional sentence), `runai_run_pipeline.sh` (the override example), `docs/bloom-integration/roadmap.md` and `docs/superpowers/**` (historical records — do not rewrite history), and `openspec/changes/archive/**`. Anything else is a miss.

- [ ] **Step 1A: No credential, token, or endpoint was introduced anywhere**

```bash
git diff main...HEAD | grep '^+' | grep -vE '^\+\+\+' | \
  grep -niE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|BEGIN CERTIFICATE|eyJ[A-Za-z0-9_-]{20,}|bearer [A-Za-z0-9._-]{20,}|client-key-data|certificate-authority-data|insecure-skip-tls-verify'
```
Expected: no output. This scans only **added** lines across the whole branch, so it catches a value pasted into any of the new docs. A `Bearer <your-token>` placeholder is fine and will not match; a real value will.

- [ ] **Step 1B: The ignore patterns still hold and shadow nothing**

```bash
git ls-files | git check-ignore --no-index --stdin 2>/dev/null
```
Expected: no output. `--no-index` is mandatory — see Task 0 Step 4.

- [ ] **Step 2: Every manifest lints**

Run through WSL — `argo` is not on PATH on the Windows side (see Task 2 Step 7):

```bash
wsl -e bash -c 'export PATH=$HOME/bin:/usr/local/bin:$PATH; \nexport KUBECONFIG=$HOME/.kube/kubeconfig-runai-busch-lab-argo-user.yaml; \ncd /mnt/c/repos/sleap-roots-pipeline; for f in *.yaml; do echo "--- $f"; argo lint "$f"; done'
```
Expected: the four stage templates and `sleap-roots-pipeline.yaml` all clean — the pipeline manifest passes online lint (verified 2026-09-15). Without VPN, drop to `--offline` and expect the one known `templateRef` artifact on `sleap-roots-pipeline.yaml`.

The `local-WSL2-*.yaml` and `local-*-test-*.yaml` files are in this glob and were never part of this change — if any errors, confirm it did so before this branch (`git stash` and re-run) before treating it as a regression.

- [ ] **Step 3: OpenSpec validates and tasks are ticked**

```bash
openspec validate fix-launcher-namespace --strict
grep -c '^- \[ \]' openspec/changes/fix-launcher-namespace/tasks.md
```
Expected: `valid`, and `0` unticked tasks.

- [ ] **Step 4: Internal links resolve**

```bash
grep -rhoE '\]\(([^)]+\.md)\)' README.md docs/cluster-identities.md \
  | sed -E 's/\]\((.*)\)/\1/' | sort -u
```
Check each path exists relative to its containing file.

- [ ] **Step 5: Open the PR**

Use `/pr-description`. Reference change-id `fix-launcher-namespace`. State plainly in the body that Phase 1 changes behavior for hand-run launches only, with the `k8s_client.py:48-49`/`:227` evidence that Bloom dispatch is unaffected.

---

## Out of scope

- Requesting a new ServiceAccount for single-cell DE work. That is a cluster-admin ask, tracked separately.
- Deciding whether DE workloads belong in `runai-busch-lab` at all given the 2-GPU quota and the live prod dispatch. A real decision, not a documentation one.
- `local-WSL2-*.yaml` variants — they reference no ServiceAccount.
- Rewriting `docs/bloom-integration/roadmap.md`'s historical entries. It is an append-only log; Task 6 corrects forward-facing docs, not the record.
