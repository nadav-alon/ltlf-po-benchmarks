#!/bin/bash

# Script to submit consolidated multi-sample benchmarks to SLURM
# Usage: ./submit_samples.sh [target1 target2 ...] [--dry-run] [--on-the-fly] 
# Targets can be: all, lucas, christian, spot, or solver:mode

# Argument parsing
TARGETS=()
DRY_RUN=false
SEMANTICS="moore"

TEST_DIR="ltlf-fin-benchmarks"
LEVEL="1-2"
SLURM_SCRIPT="test_samples_slurm.sh"
NUM_SAMPLES=10

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --semantics)
            SEMANTICS="$2"
            shift 2
            ;;
        --semantics=*)
            SEMANTICS="${1#*=}"
            shift
            ;;
        --test-dir)
            TEST_DIR="$2"
            shift 2
            ;;
        --test-dir=*)
            TEST_DIR="${1#*=}"
            shift
            ;;
        --level)
            LEVEL="$2"
            shift 2
            ;;
        --level=*)
            LEVEL="${1#*=}"
            shift
            ;;
        --num-samples)
            NUM_SAMPLES="$2"
            shift 2
            ;;
        --num-samples=*)
            NUM_SAMPLES="${1#*=}"
            shift
            ;;
        *)
            TARGETS+=("$1")
            shift
            ;;
    esac
done

# Robustness Checks
if [ ! -d "$TEST_DIR" ]; then
    echo "Error: Test directory '$TEST_DIR' not found!"
    exit 1
fi

if [[ ! " 1-2 1-4 3-4 all " =~ " $LEVEL " ]]; then
    echo "Error: Unknown level '$LEVEL'. Valid levels: 1-2, 1-4, 3-4, all"
    exit 1
fi

if [[ ! "$NUM_SAMPLES" =~ ^[0-9]+$ ]] || [ "$NUM_SAMPLES" -lt 1 ] || [ "$NUM_SAMPLES" -gt 30 ]; then
    echo "Error: Invalid number of samples '$NUM_SAMPLES'. Must be between 1 and 30."
    exit 1
fi

if [ ! -f "$SLURM_SCRIPT" ]; then
    echo "Error: Slurm script '$SLURM_SCRIPT' not found!"
    exit 1
fi

# Resolve Targets using the existing mapping in the main slurm script
META_SCRIPT="test_all_combinations_slurm.sh"
if [ ! -f "$META_SCRIPT" ]; then
    echo "Error: $META_SCRIPT not found (needed for combination mapping)!"
    exit 1
fi

SHARDS_PER_COMBINATION=$(grep "SHARDS_PER_COMBINATION=" "$META_SCRIPT" | cut -d'=' -f2)
MODES_STR=$(grep "^MODES_LONG=" "$META_SCRIPT" | sed 's/MODES_LONG=(//;s/)//' | tr -d '"')
read -a MODES <<< "$MODES_STR"

NUM_MODES=${#MODES[@]}
TASKS_PER_SAMPLE=$((NUM_MODES * SHARDS_PER_COMBINATION))

if [ ${#TARGETS[@]} -eq 0 ]; then
    TARGETS=("all")
fi

INTERNAL_RANGES=()
DESCS=()

for TARGET in "${TARGETS[@]}"; do
    FOUND=false
    if [ "$TARGET" == "all" ]; then
        INTERNAL_RANGES+=("0-$((TASKS_PER_SAMPLE - 1))")
        DESCS+=("All combinations")
        FOUND=true
    elif [[ "$TARGET" == "lucas" || "$TARGET" == "christian" || "$TARGET" == "spot" ]]; then
        START=-1
        END=-1
        for i in "${!MODES[@]}"; do
            SOLVER=$(echo ${MODES[$i]} | cut -d':' -f1)
            if [ "$SOLVER" == "$TARGET" ]; then
                if [ $START -lt 0 ]; then START=$((i * SHARDS_PER_COMBINATION)); fi
                END=$(( (i + 1) * SHARDS_PER_COMBINATION - 1 ))
            fi
        done
        if [ $START -ge 0 ]; then
            INTERNAL_RANGES+=("$START-$END")
            DESCS+=("Solver $TARGET")
            FOUND=true
        fi
    else
        for i in "${!MODES[@]}"; do
            if [ "${MODES[$i]}" == "$TARGET" ]; then
                START=$((i * SHARDS_PER_COMBINATION))
                END=$((START + SHARDS_PER_COMBINATION - 1))
                INTERNAL_RANGES+=("$START-$END")
                DESCS+=("Mode $TARGET")
                FOUND=true
                break
            fi
        done
    fi

    if [ "$FOUND" = false ]; then
        echo "Error: Unknown target '$TARGET'"
        exit 1
    fi
done

# Build Consolidated Array Range
# For each sample s (0..29), add (s * TASKS_PER_SAMPLE) to the internal ranges
FINAL_RANGES=()
for i in $(seq 0 $((NUM_SAMPLES - 1))); do
    OFFSET=$((i * TASKS_PER_SAMPLE))
    for R in "${INTERNAL_RANGES[@]}"; do
        IFS='-' read -r R_START R_END <<< "$R"
        FINAL_RANGES+=("$((R_START + OFFSET))-$((R_END + OFFSET))")
    done
done

ARRAY_RANGE=$(IFS=,; echo "${FINAL_RANGES[*]}")
DESC_STR=$(IFS=,; echo "${DESCS[*]}")

echo "========================================="
echo "Submitting Consolidated Multi-Sample Job"
echo "Targets: $DESC_STR (across $NUM_SAMPLES samples)"
echo "Semantics: $SEMANTICS"
echo "Test Dir: $TEST_DIR"
echo "Level: $LEVEL"
echo "On The Fly: both (true then false)"
echo "Range: [Optimized Array Range]"
echo "========================================="

if [ "$DRY_RUN" = true ]; then
    echo "--- DRY RUN: No job will be submitted ---"
    echo "Command that would be run:"
    echo "SEMANTICS=$SEMANTICS TEST_DIR=$TEST_DIR LEVEL=$LEVEL TASKS_PER_SAMPLE=$TASKS_PER_SAMPLE SHARDS_PER_COMBINATION=$SHARDS_PER_COMBINATION sbatch --parsable --array=$ARRAY_RANGE \"$SLURM_SCRIPT\""
else
    JOB_ID=$(sbatch --parsable --export=ALL,SEMANTICS="$SEMANTICS",TEST_DIR="$TEST_DIR",LEVEL="$LEVEL",TASKS_PER_SAMPLE="$TASKS_PER_SAMPLE",SHARDS_PER_COMBINATION="$SHARDS_PER_COMBINATION" --array=$ARRAY_RANGE "$SLURM_SCRIPT")
    if [ $? -eq 0 ]; then
        echo "✓ Job $JOB_ID submitted successfully!"
        echo "  Array tasks: $ARRAY_RANGE"
        echo ""
        echo "Monitor jobs with:"
        echo "  squeue -j $JOB_ID"
        echo ""
        echo "Check logs in (nested by Sample ID):"
        echo "  logs/${JOB_ID}/po-part-1-2_*/"
        echo ""
        echo "Results will be in:"
        echo "  results/${JOB_ID}/po-part-${LEVEL}_*/"
        echo ""
        echo "Cancel all tasks with:"
        echo "  scancel $JOB_ID"
    else
        echo "✗ Failed to submit job"
    fi
fi
