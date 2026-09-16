# Design

## Context

#70 is small in edit count — two env entries against code that already reads them — but it
introduces a failure mode that does not exist today, and the whole design question is how to
foreclose it.

Today `predict_container_digest` / `traits_container_digest` are empty. Empty is honest: it says
"this envelope does not know which image produced it." The moment a template supplies a literal
digest, a second state becomes possible — **a digest that disagrees with the image that actually
ran**. That is a *false* provenance record rather than a missing one, and it is strictly worse,
because a populated field invites trust. Provenance that lies is worse than provenance that
abstains.

The realistic path to that state is drift on a future pin bump: someone updates `image:` and does
not notice that a separate `env:` entry also encodes the image identity. Nothing would catch it,
and the resulting envelopes would be permanently, plausibly wrong.

## Goals / Non-Goals

**Goals.** Populate both fields; make image-vs-digest drift impossible to merge undetected; keep
`scripts/check_manifests.py` free of hardcoded digests.

**Non-Goals.** Adding the Argo uid/node-id vars (nothing reads them — see `proposal.md`). Changing
the idempotency key. Changing any stage's behaviour beyond what it records.

## Decision: make the `image:` line the single source of truth

Pin each producer image as `repo:tag@sha256:<digest>` and have the checker parse the digest **out
of the `image:` string**, comparing it to the env var's value.

The alternative shapes were considered and rejected:

| Option | Why not |
|---|---|
| Keep `image:` tag-only; assert only that the env var is well-formed | Nothing in the file states what digest the tag means, so the check cannot distinguish a right digest from a wrong one. It asserts presence while appearing to assert correctness — exactly the failure mode this change exists to prevent. |
| Keep `image:` tag-only; hardcode the expected digest in `check_manifests.py` | Creates a third place to update in lockstep and makes the checker itself a drift source. |
| Record the pins in a separate `image-pins.yaml` the checker reads | Moves the hardcoding rather than removing it, and adds a third source of truth. |
| Pin `image:` by digest only, dropping the tag | Loses the human-readable commit identity both templates' comments lean on heavily. |
| Pin `tag@digest` **and** resolve the tag against GHCR in the checker | Strongest guarantee, but converts an offline, fast, dependency-free checker into one needing network and registry auth; it would fail in any offline context. Registry truth is verified once, by hand, at pin time instead. |

`repo:tag@digest` is ordinary OCI reference syntax: when both are present the digest is
authoritative and the tag is decoration. This keeps one place to edit, and the assertion becomes a
tautology-free consistency check — bump either side alone and it fires.

**Trade-off accepted:** changing `image:` has a slightly larger blast radius than adding env vars
alone, since it touches how the pod obtains its bytes, and `runai-busch-lab` hosts live production.
The failure mode is the benign kind — a pull failure is immediate, total and loud
(`ImagePullBackOff` on first submit), cannot half-apply, cannot corrupt data, and reverts in one
line. Weighed against a silent wrong-digest drift that would produce permanently wrong provenance,
this is the better risk. It is de-risked further by verifying on a scratch path tree, not
`a4_poc`.

## Decision: guard against the vacuous pass

Equality alone is not sufficient. If a future edit left *both* sides absent, or both malformed,
`image_digest == env_digest` would pass trivially while proving nothing — the same class of defect
as #60's gate assertion, which passed against a gate mutated to accept every exit code.

So each producer gets three assertions, not one:

1. its `image:` reference is digest-pinned at all (`@sha256:` present),
2. its digest env var's value matches `^sha256:[0-9a-f]{64}$`,
3. the two are equal.

(1) is what stops (3) from becoming vacuous after a tag-only bump; (2) is what stops `""` from
satisfying anything.

## Decision: correct the doc claim's mechanism, not its conclusion

`docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md` lists a "pinned container
digest per run" under **required for correctness**, explaining it as "so a retry recomputes an
identical key and recognizes done work". No container digest is an input to
`compute_idempotency_key`, and line 156 of that same file already says so — the document
contradicts itself.

But the conclusion survives: the images bake `SRP_PREDICT_CODE_SHA` / `SRT_TRAITS_CODE_SHA`, and
those *are* key inputs. So a floating tag really would change the key between a run and its retry —
via the baked code SHA, not via the digest. The fix restates the mechanism and keeps the
requirement. Per this repo's recurring lesson, the claim is fixed everywhere it appears (two sites
in that file), not only where it was first noticed.

## Verification

Static assertions cannot prove a real run records a real digest, so the acceptance test is a live
submit: read `provenance.predict_container_digest` / `traits_container_digest` off the resulting
`{scan_key}.result.json` and assert each **equals the deployed image's digest**. All 12 existing
envelopes read empty, so any non-empty value is a signal — but non-blank-but-wrong is precisely the
failure this change could introduce, so "non-empty" is not the acceptance criterion.
