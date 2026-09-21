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
`scripts/check_manifests.py` free of hardcoded digests and free of network dependencies.

**Non-Goals.** Adding the Argo uid/node-id vars (nothing reads them — see `proposal.md`). Changing
the idempotency key. Changing any stage's behaviour beyond what it records. Digest-pinning the
`bloomctl`-based stages (`images-downloader`, `write-back`, `exit-gate`) — tracked separately as
[#72](https://github.com/talmolab/sleap-roots-pipeline/issues/72); this change's requirement is
deliberately narrower than "every image in the repo".

## Decision: make the `image:` line the single source of truth

Pin each producer image as `repo:tag@sha256:<digest>` and have the checker parse the digest **out
of the `image:` string**, comparing it to the env var's value.

The alternative shapes were considered and rejected:

| Option | Why not |
|---|---|
| Keep `image:` tag-only; assert only that the env var is well-formed | Nothing in the file states what digest the tag means, so the check cannot distinguish a right digest from a wrong one. It asserts presence while appearing to assert correctness — exactly the failure mode this change exists to prevent. |
| Keep `image:` tag-only; hardcode the expected digest in `check_manifests.py` | Makes the checker itself a place that must be updated in lockstep on every bump, and a place that can silently disagree with the manifest it checks. |
| Record the pins in a separate `image-pins.yaml` the checker reads | Moves the authoritative value out of the file that uses it, so the manifest and its pin can drift apart — the same problem one level removed. |
| Pin `image:` by digest only, dropping the tag | Loses the human-readable commit identity both templates' comments lean on heavily. |
| Pin `tag@digest` **and** resolve the tag against GHCR in the checker | Strongest guarantee, but converts an offline, fast, dependency-free checker into one needing network and registry auth. This repo has **no CI**, so the checker runs only when a human runs it — a network dependency makes it unrunnable in exactly the contexts where people reach for it. Registry truth is established by hand at pin time instead (tasks §1), and by the real pull (tasks §3, §7). |

Note the digest already appears in dated design docs (`2026-09-15-partial-success-exit-code-wiring-design.md:301`,
`add-partial-success-exit-gate/tasks.md:35`), so "a third source of truth" would be a miscount. The
distinction that matters is that dated design docs and archived task lists are **snapshots of a
decision**, never consulted at validation time, whereas a pins file or a hardcoded literal would be
read as current truth and could silently disagree with the manifest.

`repo:tag@digest` is ordinary OCI reference syntax: when both are present the digest is
authoritative and the tag is decoration. Measured, not assumed: `argo lint --offline` accepts the
combined form (argo v3.6.5) — and also accepts a syntactically-valid but nonexistent digest, so
lint is not a check on digest correctness.

## Why a digest rather than the commit-sha tag already in place

Both producers are *already* pinned to an immutable-looking `sha-<gitsha>` tag, so "pinning
stabilises the baked code SHA" does not by itself justify moving to a digest — a tag pin would do
that too. The residual risk a digest actually closes is recorded in this repo already, at
`sleap-roots-images-downloader-template.yaml:5-7`:

> a `sha-<gitsha>` tag is immutable in *name* only — a re-run of the build workflow against the
> same commit would silently overwrite it in GHCR unless immutable tags are enabled on that
> package; unverified from this repo

A tag names a commit; only a digest names bytes. Under a tag pin, a rebuild of the same commit can
change what runs while every reference still reads identically — including the baked
`SRP_PREDICT_CODE_SHA` / `SRT_TRAITS_CODE_SHA`, unchanged precisely because the commit is unchanged.

Note what that does and does not mean for the idempotency key, since it is easy to overstate: the
key would be **identical** either way, because the code SHA it hashes is identical. Pinning by digest
does not change key identity. What it protects is the key's *truthfulness* — without it, skip-if-done
can match a stored result against a key whose code-SHA input no longer describes the bytes that
produced it, and accept stale work as done. Provenance has the same shape: the digest is what makes
the recorded identity refer to bytes rather than to a name someone can re-point.

**Trade-off accepted:** changing `image:` has a larger blast radius than adding env vars alone,
since it touches how the pod obtains its bytes, and `runai-busch-lab` hosts live production.

**A pull failure is NOT loud, and an earlier draft of this document wrongly said it was.** This
repo's own runbook (`.claude/commands/ci-debug.md`, a file this change also edits) records the real
behaviour: a pod that cannot pull its image stays `Pending` **forever** — not `Failed`, not `Error`
— so neither `retryStrategy` nor `continueOn` applies, and because `exit-gate` is the DAG's only
leaf, an otherwise-complete batch sits `Running` indefinitely and Bloom's status poller never sees a
terminal phase. Recovery is also not "one line": reverting the repo changes nothing on the cluster,
so it needs an `argo template update`, a cluster write.

What makes the risk acceptable is therefore not that a failure would be obvious, but that a failure
is *near-impossible here*: the two digests are byte-identical to what the cluster already runs
(proven from the kubelet's own `imageID` — see tasks §6), so the apply cannot change which bytes
execute, and both references are pulled locally before the cluster is touched. The mitigation is
prevention plus the §6.2 precondition, not detection after the fact.

## Decision: guard against the vacuous pass

Equality alone is not sufficient. If a future edit left *both* sides absent, or both malformed,
`image_digest == env_digest` would pass trivially while proving nothing — the same class of defect
as #60's gate assertion, which passed against a gate mutated to accept every exit code.

So each producer gets **four** assertions, not one:

1. its `image:` reference is digest-pinned, matching `@sha256:[0-9a-f]{64}` — a presence test for
   the substring `@sha256:` would admit `@sha256:zzz`,
2. its digest env var is present exactly once,
3. that entry's value matches `^sha256:[0-9a-f]{64}$`,
4. the two are equal.

(1) is what stops (4) from becoming vacuous after a tag-only bump; (3) is what stops `""` from
satisfying anything. Critically, (4) **must not** be implemented by comparing two `None` sentinels:
a template with no parseable digest has to yield a value that can never equal an env value, or the
equality assertion prints `PASS` against today's unedited manifests and reintroduces #60's defect
inside the guard meant to prevent it.

## What these assertions do and do not prove

Stating this plainly, because overclaiming it would be the same defect in a different place.

**They prove** that the two in-file sites agree, and therefore that a *later, partial* pin bump —
the realistic drift path — cannot merge undetected.

**They do not prove** anything about registry truth. Specifically they cannot detect:

- a digest that is wrong at authoring time and copied identically into both places (a transposed
  hex character yields two equal, well-formed strings);
- a real digest belonging to a *different build* than the tag beside it, which the checker cannot
  see because it never resolves the tag;
- a digest from the wrong repository entirely.

Those are closed elsewhere, and the task plan must carry them or the guarantee has a hole:
the registry round-trip at pin time (tasks §1, which ties each digest back to its commit via
`org.opencontainers.image.revision`), a local pull of the literal reference as written (tasks §3),
and the kubelet's own `imageID` read off the running pod (tasks §7), which is the only independent
witness that the digest recorded in an envelope is the image that actually ran. A wholly fabricated
digest is partly self-catching: `image:` would then reference bytes that do not exist in that
repository, and the pull 404s.

## Decision: correct the doc claim's mechanism, not its conclusion

`docs/superpowers/specs/2026-07-06-a4-request-driven-pipeline-design.md` lists a "pinned container
digest per run" under **required for correctness**, explaining it as "so a retry recomputes an
identical key and recognizes done work". No container digest is an input to
`compute_idempotency_key`, and lines 30-33 of that same file already enumerate the key's inputs
correctly, with no digest — the document contradicts itself.

The conclusion survives, via the rebuild-behind-a-tag risk above: pinning does keep a retry's key
identical, but through the code SHA baked into a specific set of bytes, not through the digest
being hashed.

Per this repo's recurring lesson, the claim is fixed everywhere it appears rather than only where
it was noticed. The sweep found **five** sites across **three** files, and they do not all need the
same edit:

| # | site | what it says | edit |
|---|---|---|---|
| 1 | a4 design doc:190 | asserts the wrong mechanism explicitly | rewrite the mechanism |
| 2 | a4 design doc:76 | lists the requirement, states **no** mechanism | terminology only |
| 3 | a4 design doc:89 | "a pinned image digest" describing this repo's template | terminology; also false *today*, and still false for the bloomctl stages after this change |
| 4 | roadmap.md:1278 | restates §8's list, including "pinned digest" | terminology only — a different file, which is how this class of claim survives past fixes |
| 5 | a4 PoC plan:15 | "per the A4 design's per-run pin requirement" | terminology only; historical plan doc |

Sites 30-33 and 155-156 of the design doc are **counter**-sites that already state the correct
position; the correction should cite them rather than change them.
