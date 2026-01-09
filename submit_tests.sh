#!/bin/bash

# Script to submit test combinations to SLURM
# Usage: ./submit_tests.sh [all|lucas|christian|spot|solver:mode] [--dry-run]

TARGET="all"
DRY_RUN=false

# Simple argument parsing
for arg in "$@"; do
    if [ "$arg" == "--dry-run" ]; then
        DRY_RUN=true
    else
        TARGET="$arg"
    fi
done

# Configuration - read from the SLURM script to keep in sync
SLURM_SCRIPT="test_all_combinations_slurm.sh"

if [ ! -f "$SLURM_SCRIPT" ]; then
    echo "Error: $SLURM_SCRIPT not found!"
    exit 1
fi

SHARDS=$(grep "SHARDS_PER_COMBINATION=" "$SLURM_SCRIPT" | cut -d'=' -f2)
MODES_STR=$(grep "^MODES_LONG=" "$SLURM_SCRIPT" | sed 's/MODES_LONG=(//;s/)//' | tr -d '"')
read -a MODES <<< "$MODES_STR"

NUM_MODES=${#MODES[@]}
TOTAL_TASKS=$((NUM_MODES * SHARDS))

ARRAY_RANGE=""
DESC=""

if [ "$TARGET" == "all" ]; then
    ARRAY_RANGE="0-$((TOTAL_TASKS - 1))"
    DESC="All combinations ($NUM_MODES combinations x $SHARDS shards)"
elif [[ "$TARGET" == "lucas" || "$TARGET" == "christian" || "$TARGET" == "spot" ]]; then
    # Find range for a specific solver
    START=-1
    END=-1
    COUNT=0
    for i in "${!MODES[@]}"; do
        SOLVER=$(echo ${MODES[$i]} | cut -d':' -f1)
        if [ "$SOLVER" == "$TARGET" ]; then
            if [ $START -lt 0 ]; then START=$((i * SHARDS)); fi
            END=$(( (i + 1) * SHARDS - 1 ))
            COUNT=$((COUNT + 1))
        fi
    done
    if [ $START -ge 0 ]; then
        ARRAY_RANGE="$START-$END"
        DESC="Solver $TARGET ($COUNT combinations x $SHARDS shards)"
    fi
else
    # Find specific mode
    for i in "${!MODES[@]}"; do
        if [ "${MODES[$i]}" == "$TARGET" ]; then
            START=$((i * SHARDS))
            END=$((START + SHARDS - 1))
            ARRAY_RANGE="$START-$END"
            DESC="Mode $TARGET ($SHARDS shards)"
            break
        fi
    done
fi

if [ -z "$ARRAY_RANGE" ]; then
    echo "Error: Unknown target '$TARGET'"
    echo "Usage: ./submit_tests.sh [all|lucas|christian|spot|solver:mode]"
    echo ""
    echo "Available solvers: lucas, christian, spot"
    echo "Available combinations:"
    for m in "${MODES[@]}"; do echo "  - $m"; done
    exit 1
fi

echo "========================================="
echo "Submitting SLURM Job Array"
echo "Target: $DESC"
echo "========================================="
echo ""

# Create necessary directories
mkdir -p logs results

# Submit the job array
if [ "$DRY_RUN" = true ]; then
    echo "--- DRY RUN: No jobs will be submitted ---"
    echo "Command that would be run:"
    echo "sbatch --parsable --array=$ARRAY_RANGE \"$SLURM_SCRIPT\""
    JOB_ID="DRY_RUN_ID"
    EXIT_STATUS=0
else
    JOB_ID=$(sbatch --parsable --array=$ARRAY_RANGE "$SLURM_SCRIPT")
    EXIT_STATUS=$?
fi

if [ $EXIT_STATUS -eq 0 ]; then
    echo "✓ Job array submitted successfully!"
    echo "  Job ID: $JOB_ID"
    echo "  Array tasks: $ARRAY_RANGE"
    echo ""
    echo "Combinations mapping:"
    # Parse the range to filter the output
    IFS='-' read -r R_START R_END <<< "$ARRAY_RANGE"
    for i in "${!MODES[@]}"; do
        S=$((i * SHARDS))
        E=$((S + SHARDS - 1))
        # Check for overlap between [S, E] and [R_START, R_END]
        if [ $S -le $R_END ] && [ $E -ge $R_START ]; then
            printf "  Tasks %3d-%3d: %s\n" $S $E "${MODES[$i]}"
        fi
    done
    echo ""
    echo "Monitor jobs with:"
    echo "  squeue -j $JOB_ID"
    echo "  squeue -u \$USER"
    echo ""
    echo "Check logs in:"
    echo "  logs/test_all_${JOB_ID}_*.out"
    echo ""
    echo "Results will be in:"
    echo "  results/test_${JOB_ID}/"
    echo ""
    echo "Cancel all tasks with:"
    echo "  scancel $JOB_ID"
else
    echo "✗ Failed to submit job"
    exit 1
fi
