#!/usr/bin/env python3
"""Executable assertions for the cluster-access-docs spec.

Companion to `check_manifests.py`, same shape and same exit convention. That script asserts
things about the manifests; this one asserts things about the *documentation* — because the
access model is the one part of this repo that cannot be derived from the manifests, and is
therefore the part most able to drift into confident falsehood without anyone noticing.

It exists because that already happened. `docs/cluster-identities.md` shipped the sentence
"There is no per-person RunAI console access", which was never true, and the review step meant
to catch it was prose. The first attempt at a correction (PR #74) then added four more false
claims and a verification step that only checked the half of the claim where the documents
already agreed. Prose cannot check prose.

Deliberately offline: no cluster, no VPN, no credentials, no `argo` binary. Anything requiring
the live namespace belongs in `scripts/check_cluster_drift.sh`, not here — a claim about the
cluster is not a claim this repo can keep true.

Usage:  uv run python scripts/check_docs.py   # from the repo root (stdlib only)
Exit:   0 = all assertions hold, 1 = at least one failed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IDENTITIES = "docs/cluster-identities.md"
README = "README.md"
ROADMAP = "docs/bloom-integration/roadmap.md"
SKILL = ".claude/skills/runai/SKILL.md"
DRIFT_PLAN = "docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md"
CI_DEBUG = ".claude/commands/ci-debug.md"
PREDICTOR = "sleap-roots-predictor-template.yaml"
TRAIT_EXTRACTOR = "sleap-roots-trait-extractor-template.yaml"
LAUNCHER = "runai_run_pipeline.sh"
PER_RUN_SPEC ="docs/superpowers/specs/2026-09-21-per-run-run-manifest-identity-design.md"

_passes = 0
_failures: list[str] = []


def check(label: str, got, want) -> None:
    global _passes
    if got == want:
        _passes += 1
        print(f"PASS  {label}")
    else:
        _failures.append(f"{label}: got {got!r}, expected {want!r}")
        print(f"FAIL  {label}: got {got!r}, expected {want!r}")


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def norm(text: str) -> str:
    """Collapse whitespace so assertions survive line-wrapping in prose."""
    return re.sub(r"\s+", " ", text)


def text_or_empty(name: str) -> str:
    """read(), but "" for a missing file, so a check on a not-yet-written doc FAILs, not crashes."""
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def between(label: str, text: str, start: str, end: str) -> str:
    """The slice of `text` from `start` up to `end`, after checking both anchors are present.

    Anchored on text, not line numbers, so an unrelated insertion above cannot move it.
    """
    i = text.find(start)
    j = text.find(end, i + len(start)) if i != -1 else -1
    check(f"{label}: anchors found", i != -1 and j != -1, True)
    return text[i:j] if i != -1 and j != -1 else ""


def comment_block(name: str, anchor: str) -> str:
    """The `#` comment lines from the one containing `anchor` up to the first non-comment line,
    with the `#` stripped and whitespace collapsed, so a phrase survives comment wrapping."""
    lines = read(name).splitlines()
    start = next((i for i, ln in enumerate(lines) if anchor in ln), None)
    check(f"{name}: comment anchor {anchor!r} found", start is not None, True)
    if start is None:
        return ""
    block = []
    for ln in lines[start:]:
        if not ln.lstrip().startswith("#"):
            break
        block.append(ln.lstrip()[1:])
    return norm(" ".join(block))


def registered_templates() -> list[str]:
    """Stage templates the launcher registers — the repo's own inventory, not the cluster's."""
    return sorted(p.name for p in ROOT.glob("sleap-roots-*-template.yaml"))


def priority_of(template: str) -> str | None:
    m = re.search(r"^\s*priorityClassName:\s*(\S+)", read(template), re.MULTILINE)
    return m.group(1) if m else None


def main() -> int:
    ident = norm(read(IDENTITIES))
    readme = norm(read(README))
    skill = norm(read(SKILL))

    # --- Requirement: two auth planes, Scenario: retracted claims do not reappear -------------
    for label, body in (("cluster-identities", ident), ("README", readme), ("skill", skill)):
        check(
            f"{label}: no 'no per-person RunAI console access' claim",
            "no per-person RunAI console access" in body.lower(),
            False,
        )

    check(
        "skill §1: does not present KUBECONFIG as runai's only requirement",
        "needs an explicit KUBECONFIG:" in skill,
        False,
    )

    # --- Scenario: every tool's auth requirements are stated consistently ---------------------
    # runai needs BOTH planes; argo/kubectl need only the kubeconfig. The failure this catches is
    # a document naming exactly one credential for runai — which is what README did.
    check(
        "cluster-identities: runai row requires both planes",
        bool(re.search(r"\|\s*`runai`\s*\|\s*required\s*\|\s*\*\*also required\*\*\s*\|", ident)),
        True,
    )
    check(
        "cluster-identities: uses 'no' not 'n/a' as the negative token",
        "| n/a |" in ident,
        False,
    )
    check(
        "README: runai auth cell names KUBECONFIG",
        bool(re.search(r"\|\s*`runai`\s*\|[^|]*\|[^|]*KUBECONFIG[^|]*\|", readme)),
        True,
    )
    check(
        "README: runai auth cell names SSO",
        bool(re.search(r"\|\s*`runai`\s*\|[^|]*\|[^|]*SSO[^|]*\|", readme)),
        True,
    )
    check(
        "README: identity sentence does not assign one credential per tool",
        "`runai` uses your own SSO login; `argo` and `kubectl` use the shared project"
        " `argo-user` kubeconfig." in readme,
        False,
    )
    check(
        "skill §1: states runai needs an active SSO session too",
        "runai login remote-browser" in skill,
        True,
    )

    # --- Scenario: the auth-plane claims carry provenance -------------------------------------
    check(
        "cluster-identities: auth-planes section cites who confirmed it and when",
        bool(re.search(r"[Cc]onfirmed with the repo owner, 20\d\d-\d\d-\d\d", ident)),
        True,
    )

    # --- Subresource RBAC: the claim AND the command that establishes it ----------------------
    # `kubectl auth can-i get pods/log` does NOT ask about the log subresource. Everything after
    # the slash is parsed as a resource NAME, so it asks "can I get a pod named 'log'" and merely
    # mirrors bare `pods` access. Measured 2026-09-16 under both kubeconfigs: argo-user answers
    # `yes` to the slash form and `no` to `--subresource=log`. Three claims in this doc were
    # verified with the wrong command and were wrong. The doc must not teach that command, and
    # must not restate the conclusions it produced.
    check(
        "cluster-identities: auth can-i examples use --subresource, not the slash form",
        bool(re.search(r"auth can-i \w+ pods/(log|exec)", ident)),
        False,
    )
    check(
        "cluster-identities: does not claim argo-user can read logs",
        "Both `bloom-pipeline` and `argo-user` have `get pods/log`" in ident,
        False,
    )
    check(
        "cluster-identities: does not claim argo-user can exec",
        "only `argo-user` can open a shell" in ident,
        False,
    )
    # --- Per-environment dispatch (bloom#988/#863): retracted prod claims do not reappear ------
    # Bloom rewrites the stage hostPaths and the `bloom-credentials` secretName per environment,
    # and prod's trigger is on, so "prod mounts the staging Secret / has no account / is dormant"
    # are false. The roadmap is read here only for these claims.
    roadmap = norm(read(ROADMAP))
    check(
        "cluster-identities: does not claim prod mounts the staging credential",
        "mounts the **staging** Bloom credential" in ident,
        False,
    )
    check(
        "cluster-identities: does not claim the prod account was never created",
        "has never been created" in ident,
        False,
    )
    check(
        "cluster-identities: does not claim nothing drives prod",
        "nothing drives prod" in ident,
        False,
    )
    check(
        "cluster-identities: names the prod pipeline Secret",
        "genericsecret-bloom-prod-pipeline-credentials" in ident,
        True,
    )
    check(
        "README: does not claim one a4_poc tree is shared by prod/staging/manual",
        "shared by prod/staging/manual" in readme,
        False,
    )
    check(
        "roadmap: does not claim production promotion is still not next",
        "Production promotion is still NOT next" in roadmap,
        False,
    )
    check(
        "cluster-identities: does not claim Bloom fixes are on prod since 2026-10-02",
        "on Bloom prod since 2026-10-02" in ident,
        False,
    )
    check(
        "cluster-identities: states that switching dispatch off fails claimed batches",
        "switching off is a rollback, not a pause" in ident,
        True,
    )

    check(
        "cluster-identities: states that nobody can exec",
        bool(re.search(r"[Nn]obody can (open a shell|exec)", ident)),
        True,
    )
    # The correction is only useful where the reader actually runs a log command. README's
    # Troubleshooting block is that place, and it told the reader to run `argo logs` under the
    # operator kubeconfig with no hint that it cannot work -- the same claim, unfixed, one file
    # over. `argo logs` exits 0 when denied (verified 2026-09-17 under argo-user: exit 0, the
    # Forbidden on stderr, stdout empty), so this is the one denial that survives both a
    # `$?` check and a stdout pipe.
    check(
        "README: troubleshooting points at the bloom-pipeline kubeconfig for logs",
        "kubeconfig-bloom-pipeline-busch-lab.yaml" in readme,
        True,
    )
    check(
        "README: troubleshooting warns that argo logs exits 0 when denied",
        bool(re.search(r"`argo logs` exits `0` when it is denied", readme)),
        True,
    )
    check(
        "README: troubleshooting log command captures stderr",
        "argo logs <workflow-name> -n runai-busch-lab --tail 100 2>&1" in readme,
        True,
    )
    check(
        "cluster-identities: names the identity that can actually read logs",
        "`bloom-pipeline` kubeconfig" in ident,
        True,
    )

    # --- Requirement: documented inventory matches the manifests ------------------------------
    templates = registered_templates()
    check("repo has the expected template count", len(templates), 5)

    # The doc says "The three CPU stages". After #60 added the exit gate there are four non-GPU
    # stages. Derive the number rather than hardcoding it, so this fails again on the next change.
    gpu_stages = [t for t in templates if priority_of(t) == "high"]
    cpu_stages = [t for t in templates if priority_of(t) == "interactive-preemptible"]
    check("exactly one GPU stage at priorityClassName high", len(gpu_stages), 1)
    check(
        f"cluster-identities states {len(cpu_stages)} CPU stages, not a stale count",
        bool(re.search(rf"[Tt]he {_word(len(cpu_stages))} CPU stages", ident)),
        True,
    )

    # --- Scenario: documented priority classes match the templates ----------------------------
    check(
        "predictor priorityClassName matches the manifest",
        priority_of("sleap-roots-predictor-template.yaml"),
        "high",
    )
    check(
        "cluster-identities names the predictor's class correctly",
        "predictor uses `high` (125)" in ident,
        True,
    )

    # --- Scenario: no standing claim that the cluster matches the repository ------------------
    for phrase in ("No drift.", "matches this repo's file exactly"):
        check(
            f"cluster-identities: no standing cluster-parity claim ({phrase!r})",
            phrase in ident,
            False,
        )
    check(
        "cluster-identities: points at the drift-check script instead",
        "scripts/check_cluster_drift.sh" in ident,
        True,
    )

    # --- Review findings that are checkable ---------------------------------------------------
    check(
        "cluster-identities: qualifies the identity count as Kubernetes identities",
        "three Kubernetes identities" in ident,
        True,
    )
    check(
        "cluster-identities: no 'sitting behind them' containment claim",
        "sitting behind them" in ident,
        False,
    )
    check(
        "cluster-identities: does not claim the GPU stage bursts above quota",
        "that is what the `interactive-preemptible` tier below buys" in ident,
        False,
    )
    check(
        "cluster-identities: no point-in-time container uptime",
        bool(re.search(r"`Up \d+ days`", ident)),
        False,
    )
    check(
        "cluster-identities: says secret creation is self-service",
        "self-service" in ident,
        True,
    )

    # --- Superseded plan bullets --------------------------------------------------------------
    # Every false bullet in that list carries a marker, not only the one that caused this work.
    # Two markers are in use and both are correct: blockquoted "SUPERSEDED" for a *step* (line
    # 352, PR #69) and inline "Corrected <date>" for a *bullet* (line 605, PR #60). These are
    # bullets, so either form counts — the assertion is that the claim is marked, not how.
    # Anchored on the claim text, not the line number: an earlier version of this assertion keyed
    # on lines 599/600/605 and broke the moment a paragraph was inserted above them. A test that
    # fails when an unrelated edit shifts a file is a test that gets deleted.
    plan_lines = read(DRIFT_PLAN).splitlines()
    false_bullets = {
        "bloom-pipeline can read logs": "You will not get pod logs through the Bloom path",
        "no per-person console access": "There is no per-person RunAI console access;",
        "unset priority class": "Deserved GPU quota is 2.",
    }
    for name, claim in false_bullets.items():
        hits = [ln for ln in plan_lines if claim in ln]
        check(f"drift plan: the {name!r} bullet is still present to annotate", len(hits), 1)
        marked = hits and (
            "SUPERSEDED" in hits[0] or re.search(r"Corrected 20\d\d-\d\d-\d\d", hits[0])
        )
        check(f"drift plan: {name!r} bullet carries a correction marker", bool(marked), True)

    # --- Predictor GPU container target (#117) -------------------------------------------
    # Not part of the cluster-access-docs spec: these guard the per-batch-pipeline predictor
    # requirement's documentation. gpu-memory alone sent the GPU to Argo's `wait` sidecar while
    # every doc said the annotation was the whole story, so assert each place that describes the
    # predictor's GPU request names the container too. The canonical explanation is the comment
    # beside the annotation in sleap-roots-predictor-template.yaml; these docs point there.
    check(
        "README no longer says gpu-memory alone grants GPU access",
        "GPU access comes entirely from the" in norm(read(README)),
        False,
    )
    gpu_docs = [
        README,
        SKILL,
        "openspec/project.md",
        ".claude/commands/ci-debug.md",
        ".claude/commands/review-pr.md",
        ".claude/commands/review-openspec.md",
        ".claude/commands/docs-review.md",
    ]
    for name in gpu_docs:
        check(
            f"{name} names gpu-fraction-container-name",
            "gpu-fraction-container-name" in read(name),
            True,
        )
        # The annotation is ignored below Run:ai 2.24 (this cluster: 2.22). What works today is
        # the podSpecPatch reorder, so every doc that describes the GPU request must name it --
        # a doc naming only the annotation teaches a fix that does nothing on this cluster.
        check(f"{name} names the podSpecPatch reorder", "podSpecPatch" in read(name), True)
    check(
        "README does not claim the annotation alone directs the GPU to main",
        "to direct it to the predict container" in norm(read(README)),
        False,
    )
    # Presence of "podSpecPatch" is not enough: a doc can name it while calling it optional. Reject
    # the phrasings that would teach a reader to drop it, in every doc above.
    dismissive = re.compile(
        r"podSpecPatch[^.|]{0,60}\b(cosmetic|optional|not needed|unnecessary|can be removed)\b"
        r"|annotation alone (works|is enough|suffices)",
        re.IGNORECASE,
    )
    check(
        "no GPU doc calls the podSpecPatch optional or the annotation sufficient",
        [n for n in gpu_docs if dismissive.search(norm(read(n)))],
        [],
    )
    # Run:ai applies gpu-memory in MB of 10^6 bytes: "8192" became RUNAI_GPU_MEMORY_LIMIT=8192000000
    # in every probe pod (#117), i.e. 7,813 MiB, not 8,192. These are the phrasings that said MiB.
    stale_units = {
        README: "absolute amount of GPU memory (MiB)",
        "openspec/project.md": "absolute MiB",
        ".claude/commands/ci-debug.md": "absolute **MiB**",
        SKILL: '`gpu-memory: "8192"` (MiB)',
    }
    check(
        "no doc gives gpu-memory in MiB (Run:ai applies MB)",
        [n for n, phrase in stale_units.items() if phrase in norm(read(n))],
        [],
    )
    # The pre-#25 review checklists ("`gpu-fraction`; `nvidia.com/gpu` on the predictor") are
    # worded three ways across two files, so match the pairing, not one sentence.
    stale_checklist = re.compile(r"`?gpu-fraction`?\s*[,;]\s*`?nvidia\.com/gpu")
    check(
        "no command checklist still pairs gpu-fraction with nvidia.com/gpu",
        [
            p.name
            for p in sorted((ROOT / ".claude/commands").glob("*.md"))
            if stale_checklist.search(norm(p.read_text(encoding="utf-8")))
        ],
        [],
    )

    # --- Production runbook and the operating facts it relies on (add-production-runbook) -----
    # Claim-wide: each fact is checked in every doc that states it, not only the one first found.
    roadmap = norm(read(ROADMAP))

    # Shared-tree hazards. The no-run-id rule and the pre-a9 rollback hazard apply to both
    # environments' trees: a4_poc (staging) and bloom_cyl_pipeline/prod (prod, since bloom#988).
    check(
        "roadmap: no-run-id rule anchor appears once",
        roadmap.count("never point a no-run-id"),
        1,
    )
    rule = between("roadmap no-run-id rule", roadmap, "never point a no-run-id", "use a scratch tree")
    check("roadmap: no-run-id rule names staging's shared tree", "a4_poc" in rule, True)
    check(
        "roadmap: no-run-id rule names prod's shared tree",
        "bloom_cyl_pipeline/prod" in rule,
        True,
    )
    deliberate = between(
        "roadmap Deliberate bullet", roadmap, "**Deliberate:** a bloomctl rollback", "- **Covered:**"
    )
    check(
        "roadmap: Deliberate rollback bullet names bloom_cyl_pipeline/prod",
        "bloom_cyl_pipeline/prod" in deliberate,
        True,
    )
    a4_only = re.compile(r"shared `a4_poc` trees?(?![^.]*bloom_cyl_pipeline/prod)")
    a4_only_docs = [ROADMAP, PER_RUN_SPEC, SKILL]
    check(
        "no doc limits the no-run-id rule to a4_poc",
        [n for n in a4_only_docs if a4_only.search(norm(read(n)))],
        [],
    )
    skill_6 = between("runai SKILL §6", read(SKILL), "## 6.", "## 7.")
    check("runai SKILL §6 names the no-run-id rule", "no-run-id" in skill_6, True)
    check(
        "runai SKILL §6 links the roadmap rule",
        "](../../../docs/bloom-integration/roadmap.md" in skill_6,
        True,
    )

    # A missing hostPath directory leaves the pod Pending and the Workflow hung; it never fails
    # startup (cluster-identities, "Storage is three hand-made directories"). Both word orders.
    startup_fail = re.compile(r"fails? (pod )?startup|fails at startup|startup fails", re.IGNORECASE)
    startup_docs = ["openspec/project.md", README, CI_DEBUG]
    check(
        "no doc says a missing hostPath fails pod startup",
        [n for n in startup_docs if startup_fail.search(norm(read(n)))],
        [],
    )
    pending_rows = [ln for ln in read(CI_DEBUG).splitlines() if "stuck `Pending` (any stage)" in ln]
    check("ci-debug: Pending row anchor appears once", len(pending_rows), 1)
    pending_row = pending_rows[0] if pending_rows else ""
    check(
        "ci-debug: Pending row does not recommend retryStrategy",
        "add `retryStrategy`" in pending_row,
        False,
    )
    check(
        "ci-debug: Pending row links cluster-identities",
        "cluster-identities.md" in pending_row,
        True,
    )

    # Failure evidence: Bloom stamps ttlStrategy from WORKFLOWS_K8S_TTL_SECONDS on every cyl
    # Workflow, so its pods and logs are gone within that window (#137). Every place that sends
    # a reader to pod logs says so.
    ttl_named = re.compile(r"WORKFLOWS_K8S_TTL_SECONDS|issues/137(?!\d)")
    ident_raw = read(IDENTITIES)
    p = ident_raw.find("**Pod logs need the `bloom-pipeline` kubeconfig")
    check("cluster-identities: pod-log paragraph anchor found", p != -1, True)
    pod_log_para = ident_raw[p : ident_raw.find("\n\n", p)] if p != -1 else ""
    check(
        "cluster-identities: pod-log paragraph names the TTL window",
        bool(ttl_named.search(pod_log_para)),
        True,
    )
    ci_a = between("ci-debug §A", read(CI_DEBUG), "## A.", "## B.")
    check("ci-debug §A: links #137", "issues/137" in ci_a, True)
    readme_raw = read(README)
    troubleshooting = between("README Troubleshooting", readme_raw, "## 🐛 Troubleshooting", "\n## ")
    check("README Troubleshooting: links #137", "issues/137" in troubleshooting, True)
    argo_rows = [ln for ln in ident_raw.splitlines() if ln.startswith("| **`argo-user`**")]
    check("cluster-identities: argo-user row appears once", len(argo_rows), 1)
    argo_can = argo_rows[0].strip("|").split("|")[2] if argo_rows else ""
    check(
        "cluster-identities: argo-user Can cell lists get/list/watch workflows",
        "`get`/`list`/`watch workflows`" in argo_can,
        True,
    )
    # Since contracts a9 each run has its own manifest; the legacy file no longer accumulates.
    cumulative = re.compile(r"cumulative across every run|accumulates scan_keys[\s#]+across every run")
    check(
        "no doc calls the legacy manifest cumulative",
        [n for n in (README, PREDICTOR) if cumulative.search(read(n))],
        [],
    )
    # Environments differ by label, stage root and Secret since bloom#988, not by label alone.
    check(
        "runai_run_pipeline.sh: environments not 'distinguished only by an environment label'",
        bool(re.search(r"distinguished only[\s#]+by an environment label", read(LAUNCHER))),
        False,
    )

    # The wheat/sorghum rollback starts with unlink(), which also drops `candidate` and `latest`
    # (training#72; roadmap, 2026-10-05 entry). The template comment owns that procedure.
    trait_rollback = comment_block(TRAIT_EXTRACTOR, "Rollback (updated 2026-10-04, #119)")
    check(
        "trait-extractor rollback comment names unlink's candidate side effect",
        bool(re.search(r"unlink\(\)[^.]*candidate", trait_rollback)),
        True,
    )

    if _failures:
        print(f"\n=== {len(_failures)} FAILED, {_passes} passed ===")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"\n=== ALL {_passes} ASSERTIONS PASS ===")
    return 0


def _word(n: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))


if __name__ == "__main__":
    sys.exit(main())
