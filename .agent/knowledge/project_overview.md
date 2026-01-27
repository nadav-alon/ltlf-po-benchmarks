# Project Knowledge: LTLf PO Benchmarks

## Overview
This project is a benchmarking suite for Linear Temporal Logic on Finite Traces (LTLf) synthesis, specifically focusing on Partial Observability (PO). It compares different synthesis approaches and tools across various benchmarks.

## Solvers & Modes
- **Lucas Syft**:
    - `belief-states`: Handles PO via belief state construction.
    - `mso`: Monadic Second-Order logic approach.
    - `projection-based`: Alternative PO technique.
- **Christian Syft**: Secondary solver implementation.
- **Spot**: Industry-standard LTL tools (`ltlfsynt`, `ltlsynt`, `ltlfilt`).

## Key Scripts
- `runTests.py`: Main driver for running benchmarks. Features:
    - Sharding (`--shard-id`, `--num-shards`) for parallel execution.
    - Result logging and controller (HOA) extraction.
    - Preprocessing with MONA tools.
- `visualize.py`: Script for generating scatter plots and performance comparisons.
- `submit_tests.sh`: Slurm-compatible submission script for HPC environments.

## Preprocessing Pipeline
The Lucas solver pipeline involves:
1. `ltlf2fol` or `ltlf2pfol` to convert LTLf to MONA input.
2. `mona` to compile DFAs.
3. Dynamic quantification or negation depending on the mode (`mso` vs `projection-based`).

## Environment Notes
- **WSL Support**: The project is developed within a WSL environment, and run on an HPC cluster (Slurm).
- **Data Storage**: Large result sets are stored/sharded in `/home/cowclaw/results_shards`.
