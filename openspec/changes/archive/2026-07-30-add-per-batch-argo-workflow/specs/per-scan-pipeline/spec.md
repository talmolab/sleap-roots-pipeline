## REMOVED Requirements

### Requirement: Two-stage warm-predict → traits DAG

**Reason**: Superseded by `per-batch-pipeline`'s four-stage DAG
(`images-downloader → predictor → trait-extractor → write-back`), which adds the automated
stage-in and write-back tasks this requirement's two-task shape had no room for.
**Migration**: See `per-batch-pipeline`'s "Four-stage per-batch DAG" requirement.

### Requirement: Predictor runs the warm GHCR predict container

**Reason**: The predictor template's contract is unchanged, but it now belongs to the
`per-batch-pipeline` capability rather than a capability describing a two-task, single-scan flow.
**Migration**: Carried forward verbatim as `per-batch-pipeline`'s "Predictor runs the warm GHCR
predict container" requirement — no behavior change.

### Requirement: Trait-extractor runs the GHCR trait-extractor image

**Reason**: Same as above — contract unchanged, capability renamed.
**Migration**: Carried forward verbatim as `per-batch-pipeline`'s "Trait-extractor runs the GHCR
trait-extractor image" requirement — no behavior change.

### Requirement: Producer images are pinned, and the launcher registers only the two templates

**Reason**: The launcher now registers four templates, not two, and image-pinning is now stated
per bloomctl-based task rather than as a single combined "producer" requirement.
**Migration**: See `per-batch-pipeline`'s "bloomctl-based tasks pin their image and mount
credentials deterministically" and "Launcher registers all four templates" requirements. Producer
image pinning (predict/traits) is preserved unchanged in the carried-forward predictor/
trait-extractor requirements.
