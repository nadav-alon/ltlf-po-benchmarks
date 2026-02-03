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

if [[ ! " part 1-2 1-4 3-4 all " =~ " $LEVEL " ]]; then
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

SHORT_INTERNAL_RANGES=()
LONG_INTERNAL_RANGES=()
DESCS=()

# Split point: First 6 modes (0-5) are Lucas/Christian (Short), last 3 are Spot (Long)
SPLIT_IDX=$((6 * SHARDS_PER_COMBINATION))

for TARGET in "${TARGETS[@]}"; do
    FOUND=false
    if [ "$TARGET" == "all" ]; then
        SHORT_INTERNAL_RANGES+=("0-$((SPLIT_IDX - 1))")
        LONG_INTERNAL_RANGES+=("${SPLIT_IDX}-$((TASKS_PER_SAMPLE - 1))")
        DESCS+=("All tools")
        FOUND=true
    elif [[ "$TARGET" == "lucas" || "$TARGET" == "christian" ]]; then
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
            SHORT_INTERNAL_RANGES+=("$START-$END")
            DESCS+=("Solver $TARGET")
            FOUND=true
        fi
    elif [ "$TARGET" == "spot" ]; then
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
            LONG_INTERNAL_RANGES+=("$START-$END")
            DESCS+=("Solver $TARGET")
            FOUND=true
        fi
    else
        for i in "${!MODES[@]}"; do
            if [ "${MODES[$i]}" == "$TARGET" ]; then
                START=$((i * SHARDS_PER_COMBINATION))
                END=$((START + SHARDS_PER_COMBINATION - 1))
                if [ $START -lt $SPLIT_IDX ]; then
                    SHORT_INTERNAL_RANGES+=("$START-$END")
                else
                    LONG_INTERNAL_RANGES+=("$START-$END")
                fi
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

# Function to build final ranges for a bucket
build_final_range() {
    local INTERNAL_RANGES=("$@")
    local FINAL_RANGES=()
    for i in $(seq 0 $((NUM_SAMPLES - 1))); do
        OFFSET=$((i * TASKS_PER_SAMPLE))
        for R in "${INTERNAL_RANGES[@]}"; do
            IFS='-' read -r R_START R_END <<< "$R"
            FINAL_RANGES+=("$((R_START + OFFSET))-$((R_END + OFFSET))")
        done
    done
    echo $(IFS=,; echo "${FINAL_RANGES[*]}")
}

SHORT_ARRAY_RANGE=$(build_final_range "${SHORT_INTERNAL_RANGES[@]}")
LONG_ARRAY_RANGE=$(build_final_range "${LONG_INTERNAL_RANGES[@]}")
DESC_STR=$(IFS=,; echo "${DESCS[*]}")

echo "========================================="
echo "Submitting Consolidated Multi-Sample Job"
echo "Targets: $DESC_STR (across $NUM_SAMPLES samples)"
echo "Semantics: $SEMANTICS"
echo "Test Dir: $TEST_DIR"
echo "Level: $LEVEL"
echo "Timing: Lucas/Christian (3.5h), Spot (6.5h)"
echo "========================================="

submit_job() {
    local RANGE=$1
    local TIME=$2
    local LABEL=$3
    
    if [ -z "$RANGE" ]; then return 0; fi

    echo "Submitting $LABEL Job..."
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] sbatch --time=$TIME --array=$RANGE $SLURM_SCRIPT"
        return 0
    fi

    JOB_ID=$(sbatch --parsable --export=ALL,SEMANTICS="$SEMANTICS",TEST_DIR="$TEST_DIR",LEVEL="$LEVEL",TASKS_PER_SAMPLE="$TASKS_PER_SAMPLE",SHARDS_PER_COMBINATION="$SHARDS_PER_COMBINATION" --time="$TIME" --array="$RANGE" "$SLURM_SCRIPT")
    
    if [ $? -eq 0 ]; then
        echo "  ✓ Job $JOB_ID submitted successfully! ($TIME limit)"
        echo "    Array tasks: $RANGE"
    else
        echo "  ✗ Failed to submit $LABEL job"
    fi
}

submit_job "$SHORT_ARRAY_RANGE" "03:30:00" "SHORT (Lucas/Christian)"
submit_job "$LONG_ARRAY_RANGE" "06:30:00" "LONG (Spot)"

if [ "$DRY_RUN" != true ]; then
    echo ""
    echo "Monitor jobs with: squeue -u $USER"
    echo "Results will be in: results/<JOB_ID>/po-part-${LEVEL}_*/"
fi
