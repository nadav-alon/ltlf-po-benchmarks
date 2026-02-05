#!/bin/bash
#SBATCH --job-name=ltlf_po_multi
#SBATCH --output=logs/slurm_multi_%A_%a.out
#SBATCH --error=logs/slurm_multi_%A_%a.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=06:30:00
#SBATCH --exclude=cn[31-44],gpu[1-4],gpu[6-8]
# #SBATCH --array=0-4319

# Configuration
TIMEOUT=${TIMEOUT:-180}
LUCAS_PATH="~/work/lucas/Syft/build/bin/Syft"
CHRISTIAN_PATH="~/work/ltlf-synth-unrel-input-aaai2025/Syft/build/bin/Syft"

# Local Spot installation
export PATH="$PWD/spot/local/bin:$PATH"
export LD_LIBRARY_PATH="$PWD/spot/local/lib:$LD_LIBRARY_PATH"

# Number of shards per combination
SHARDS_PER_COMBINATION=${SHARDS_PER_COMBINATION:-16}
TASKS_PER_SAMPLE=${TASKS_PER_SAMPLE:-144}

# Semantics (default to moore if not set)
SEMANTICS=${SEMANTICS:-"moore"}
TEST_DIR=${TEST_DIR:-"ltlf-fin-benchmarks"}
LEVEL=${LEVEL:-"1-2"}

# --- Multi-Sample Decoding Logic ---
# The $SLURM_ARRAY_TASK_ID covers 144 tasks per sample.
# Example: 
#   Tasks 0-143    -> Sample 1
#   Tasks 144-287  -> Sample 2
#   ...
#   Tasks 4176-4319 -> Sample 30

SAMPLE_ID=$(($SLURM_ARRAY_TASK_ID / $TASKS_PER_SAMPLE + 1))
INTERNAL_ID=$(($SLURM_ARRAY_TASK_ID % $TASKS_PER_SAMPLE))

# Dynamically set the PART_DIR based on the decoded Sample ID and LEVEL
if [ "$LEVEL" = "all" ]; then
    PART_DIR="po-part-all"
elif [ "$LEVEL" = "part" ]; then
    PART_DIR="part"
else
    PART_DIR="po-part-${LEVEL}_${SAMPLE_ID}"
fi

# Define all combinations
MODES_LONG=("lucas:belief-states" "lucas:projection-based" "lucas:mso" "christian:direct" "christian:belief" "christian:mso" "spot:ltlf" "spot:ltl" "spot:ltlfilt")

# Calculate combination and shard index from INTERNAL_ID
COMBINATION_ID=$(($INTERNAL_ID / $SHARDS_PER_COMBINATION))
SHARD_ID=$(($INTERNAL_ID % $SHARDS_PER_COMBINATION))

MODE_LONG=${MODES_LONG[$COMBINATION_ID]}
SOLVER=$(echo $MODE_LONG | cut -d':' -f1)

# Set the correct path based on solver
if [ "$SOLVER" = "spot" ]; then
    SYFT_PATH="."
else
    if [ "$SOLVER" = "lucas" ]; then
        SYFT_PATH=$LUCAS_PATH
    else
        SYFT_PATH=$CHRISTIAN_PATH
    fi
fi

# Unique output file per shard
SAFE_MODE=$(echo $MODE_LONG | tr ':' '_')

# Get the base Job ID
BASE_JOB_ID=${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}
TASK_ID=$SLURM_ARRAY_TASK_ID

# Results and logs are nested by PART_DIR (Sample ID) to avoid collisions
mkdir -p "logs/${BASE_JOB_ID}/${PART_DIR}" "results/${BASE_JOB_ID}/${PART_DIR}/${SAFE_MODE}"
exec > "logs/${BASE_JOB_ID}/${PART_DIR}/ltlf_po_${BASE_JOB_ID}_${TASK_ID}.out" 2>&1

OUTPUT_FILE="results/${BASE_JOB_ID}/${PART_DIR}/${SAFE_MODE}/shard_${SHARD_ID}.csv"

echo "========================================="
echo "SLURM Job ID: $SLURM_JOB_ID"
echo "SLURM Array Job ID: ${SLURM_ARRAY_JOB_ID:-N/A}"
echo "Array Task ID: $SLURM_ARRAY_TASK_ID"
echo "Decoded Sample ID: $SAMPLE_ID"
echo "Decoded Internal ID: $INTERNAL_ID"
echo "Running on node: $(hostname)"
echo "Testing: $MODE_LONG"
echo "Semantics: $SEMANTICS"
echo "Test Dir: $TEST_DIR"
echo "Part Dir: $PART_DIR"
echo "On The Fly: $ON_THE_FLY"
echo "Shard: $SHARD_ID of $SHARDS_PER_COMBINATION"
echo "Output file: $OUTPUT_FILE"
echo "========================================="
echo ""

# Run the tests sequentially (on-the-fly=true and on-the-fly=false)
# We use 'timeout' to ensure each run has a fair share (exactly 3 hours each if needed)
SOFT_TIMEOUT="3h"

# Run the tests. 
# For Spot, we run both on-the-fly=true and on-the-fly=false for comparison.
# For other tools, we only run once as the flag doesn't affect them.
if [ "$SOLVER" = "spot" ]; then
    OTF_VARIANTS="true false"
else
    OTF_VARIANTS="true"
fi

for OTF_VAL in $OTF_VARIANTS; do
    SUFFIX="otf"
    if [ "$OTF_VAL" = "false" ]; then SUFFIX="off"; fi
    
    # For non-spot solvers, we don't need a suffix since there's only one run
    if [ "$SOLVER" != "spot" ]; then
        OUTPUT_FILE="results/${BASE_JOB_ID}/${PART_DIR}/${SAFE_MODE}/shard_${SHARD_ID}.csv"
    else
        OUTPUT_FILE="results/${BASE_JOB_ID}/${PART_DIR}/${SAFE_MODE}/shard_${SHARD_ID}_${SUFFIX}.csv"
    fi
    
    echo "-----------------------------------------"
    echo "Running with ON_THE_FLY=$OTF_VAL"
    echo "Timeout: $SOFT_TIMEOUT"
    echo "Output: $OUTPUT_FILE"
    echo "-----------------------------------------"
    
    # Run the test
    timeout $SOFT_TIMEOUT python3 runTests.py \
        --mode=$MODE_LONG \
        --test-dir=$TEST_DIR \
        --path=$SYFT_PATH \
        --timeout=$TIMEOUT \
        --output=$OUTPUT_FILE \
        --shard-id=$SHARD_ID \
        --num-shards=$SHARDS_PER_COMBINATION \
        --semantics=$SEMANTICS \
        --part-dir=$PART_DIR \
        --on-the-fly=$OTF_VAL \
        --sample-id=$SAMPLE_ID \
        ${LIMIT:+--limit=$LIMIT}

    RET=$?
    if [ $RET -eq 124 ]; then
        echo "✗ Test timed out after $SOFT_TIMEOUT"
    elif [ $RET -ne 0 ]; then
        echo "✗ Test failed with exit code: $RET"
    else
        echo "✓ Test completed successfully"
    fi
    echo ""
done

exit 0
