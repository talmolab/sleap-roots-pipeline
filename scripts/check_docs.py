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

Usage:  python scripts/check_docs.py      # from the repo root
Exit:   0 = all assertions hold, 1 = at least one failed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IDENTITIES = "docs/cluster-identities.md"
README = "README.md"
SKILL = ".claude/skills/runai/SKILL.md"
DRIFT_PLAN = "docs/superpowers/plans/2026-09-15-cluster-identities-and-namespace-drift.md"

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
    plan = read(DRIFT_PLAN).splitlines()
    for lineno in (599, 600, 605):
        line = plan[lineno - 1] if lineno <= len(plan) else ""
        check(
            f"{DRIFT_PLAN}:{lineno} carries a superseded marker",
            "SUPERSEDED" in line,
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
