#!/bin/bash

# Script to submit test combinations to SLURM
# Usage: ./submit_tests.sh [target1 target2 ...] [--dry-run] [--email your@email.com]
# Targets can be: all, lucas, christian, spot, or solver:mode

# Argument parsing
TARGETS=()
DRY_RUN=false
SEMANTICS="moore"
NUM_USELESS_UNOBSERVABLES=0
TEST_DIR="lucas"
PART_DIR="part"
EMAIL="alonadav2000@gmail.com"
ON_THE_FLY=true

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
        --num-useless-unobs)
            NUM_USELESS_UNOBSERVABLES="$2"
            shift 2
            ;;
        --num-useless-unobs=*)
            NUM_USELESS_UNOBSERVABLES="${1#*=}"
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
        --part-dir)
            PART_DIR="$2"
            shift 2
            ;;
        --part-dir=*)
            PART_DIR="${1#*=}"
            shift
            ;;
        --on-the-fly)
            ON_THE_FLY=true
            shift
            ;;
        --on-the-fly=*)
            ON_THE_FLY="${1#*=}"
            shift
            ;;
        --mail|--email)
            EMAIL="$2"
            shift 2
            ;;
        --mail=*|--email=*)
            EMAIL="${1#*=}"
            shift
            ;;
        *)
            TARGETS+=("$1")
            shift
            ;;
    esac
done

export SEMANTICS
export NUM_USELESS_UNOBSERVABLES
export TEST_DIR
export PART_DIR
export ON_THE_FLY

# If no targets provided, default to all
if [ ${#TARGETS[@]} -eq 0 ]; then
    TARGETS=("all")
fi

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

ARRAY_RANGES=()
DESCS=()

for TARGET in "${TARGETS[@]}"; do
    FOUND=false
    if [ "$TARGET" == "all" ]; then
        ARRAY_RANGES+=("0-$((TOTAL_TASKS - 1))")
        DESCS+=("All combinations")
        FOUND=true
    elif [[ "$TARGET" == "lucas" || "$TARGET" == "christian" || "$TARGET" == "spot" ]]; then
        # Find range for a specific solver
        START=-1
        END=-1
        for i in "${!MODES[@]}"; do
            SOLVER=$(echo ${MODES[$i]} | cut -d':' -f1)
            if [ "$SOLVER" == "$TARGET" ]; then
                if [ $START -lt 0 ]; then START=$((i * SHARDS)); fi
                END=$(( (i + 1) * SHARDS - 1 ))
            fi
        done
        if [ $START -ge 0 ]; then
            ARRAY_RANGES+=("$START-$END")
            DESCS+=("Solver $TARGET")
            FOUND=true
        fi
    else
        # Find specific mode
        for i in "${!MODES[@]}"; do
            if [ "${MODES[$i]}" == "$TARGET" ]; then
                START=$((i * SHARDS))
                END=$((START + SHARDS - 1))
                ARRAY_RANGES+=("$START-$END")
                DESCS+=("Mode $TARGET")
                FOUND=true
                break
            fi
        done
    fi

    if [ "$FOUND" = false ]; then
        echo "Error: Unknown target '$TARGET'"
        echo "Usage: ./submit_tests.sh [all|lucas|christian|spot|solver:mode] [--dry-run] [--email your@email.com] [--on-the-fly]"
        echo ""
        echo "Available solvers: lucas, christian, spot"
        echo "Available combinations:"
        for m in "${MODES[@]}"; do echo "  - $m"; done
        exit 1
    fi
done

# Join ranges with commas
ARRAY_RANGE=$(IFS=,; echo "${ARRAY_RANGES[*]}")
DESC_STR=$(IFS=,; echo "${DESCS[*]}")

echo "========================================="
echo "Submitting SLURM Job Array"
echo "Targets: $DESC_STR"
echo "Semantics: $SEMANTICS"
echo "Useless Unobs: $NUM_USELESS_UNOBSERVABLES"
echo "Test Dir: $TEST_DIR"
echo "Part Dir: $PART_DIR"
echo "On The Fly: $ON_THE_FLY"
echo "Range: $ARRAY_RANGE"
if [ -n "$EMAIL" ]; then
    echo "Email: $EMAIL (will notify on completion)"
fi
echo "========================================="
echo ""

# Submission block
if [ "$DRY_RUN" = true ]; then
    echo "--- DRY RUN: No jobs will be submitted ---"
    echo "Command that would be run:"
    echo "SEMANTICS=$SEMANTICS NUM_USELESS_UNOBSERVABLES=$NUM_USELESS_UNOBSERVABLES TEST_DIR=$TEST_DIR PART_DIR=$PART_DIR ON_THE_FLY=$ON_THE_FLY sbatch --parsable --array=$ARRAY_RANGE \"$SLURM_SCRIPT\""
    if [ -n "$EMAIL" ]; then
        echo "Notification that would be scheduled: sbatch --dependency=afterany:JOB_ID --mail-type=END --mail-user=$EMAIL ..."
    fi
    JOB_ID="DRY_RUN_ID"
    EXIT_STATUS=0
else
    JOB_ID=$(sbatch --parsable --export=ALL,SEMANTICS="$SEMANTICS",NUM_USELESS_UNOBSERVABLES="$NUM_USELESS_UNOBSERVABLES",TEST_DIR="$TEST_DIR",PART_DIR="$PART_DIR",ON_THE_FLY="$ON_THE_FLY" --array=$ARRAY_RANGE "$SLURM_SCRIPT")
    EXIT_STATUS=$?
fi

if [ $EXIT_STATUS -eq 0 ]; then
    echo "✓ Job array submitted successfully!"
    echo "  Job ID: $JOB_ID"
    echo "  Array tasks: $ARRAY_RANGE"
    echo ""
    echo "Combinations mapping for selected range:"
    
    # Simple overlap check for display
    for i in "${!MODES[@]}"; do
        S=$((i * SHARDS))
        E=$((S + SHARDS - 1))
        
        SHOW=false
        # Check if this mode's range is covered by ANY of the requested ranges
        for R in "${ARRAY_RANGES[@]}"; do
            IFS='-' read -r R_START R_END <<< "$R"
            if [ $S -le $R_END ] && [ $E -ge $R_START ]; then
                SHOW=true
                break
            fi
        done
        
        if [ "$SHOW" = true ]; then
            printf "  Tasks %3d-%3d: %s\n" $S $E "${MODES[$i]}"
        fi
    done
    echo ""
    echo "Monitor jobs with:"
    echo "  squeue -j $JOB_ID"
    echo "  squeue -u \$USER"
    echo ""
    echo "Check logs in:"
    echo "  logs/$JOB_ID/ltlf_po_${JOB_ID}_*.out"
    echo ""
    echo "Results will be in:"
    echo "  results/$JOB_ID/"
    echo ""
    echo "Cancel all tasks with:"
    echo "  scancel $JOB_ID"

    if [ -n "$EMAIL" ] && [ "$DRY_RUN" = false ]; then
        # Submit a notification job that depends on the entire array finishing
        # We use afterany so it triggers even if some tasks fail
        NOTIFY_JOB_ID=$(sbatch --parsable --dependency=afterany:$JOB_ID --job-name="notify_${JOB_ID}" --mail-type=END --mail-user="$EMAIL" --wrap="echo 'Job array $JOB_ID ($DESC_STR) has completed.'")
        if [ $? -eq 0 ]; then
            echo ""
            echo "✉ Completion notification scheduled for $EMAIL"
            echo "  Notification Job ID: $NOTIFY_JOB_ID"
        else
            echo ""
            echo "⚠ Warning: Failed to schedule email notification"
        fi
    fi
else
    echo "✗ Failed to submit job"
    exit 1
fi
