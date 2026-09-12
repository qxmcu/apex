# APEX Benchmark Reproduction Suite

This folder provides automated scripts and command recipes to reproduce all benchmark figures published in the APEX documentation.

## Automated Reproduction

Run the single automated script:

```bash
bash benchmarks/reproduce.sh
```

This will:
1. Download the Canterbury Corpus (`cantrbry.tar.gz`) from the official University of Canterbury archive.
2. Extract and concatenate it into a 282 MB scaled test binary (`canterbury_scaled.bin`).
3. Query system CPU and RAM specifications.
4. Execute `apex benchmark canterbury_scaled.bin` across all candidate engines.
5. Print throughput, compression ratios, and byte-reduction stats.

## Manual Commands

Refer to [docs/BENCHMARKS.md](../docs/BENCHMARKS.md) for full parameters, competitor commands, and methodology.
