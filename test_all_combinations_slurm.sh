#!/bin/bash
#SBATCH --job-name=ltlf_po
#SBATCH --output=logs/slurm_%A_%a.out
#SBATCH --error=logs/slurm_%A_%a.err
#SBATCH --array=0-159
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --exclude=cn[31-44],gpu[1-4],gpu[6-8]

# Configuration
TIMEOUT=180
TEST_DIR="lucas"
LUCAS_PATH="~/work/lucas/Syft/build/bin/Syft"
CHRISTIAN_PATH="~/work/ltlf-synth-unrel-input-aaai2025/Syft/build/bin/Syft"

# Local Spot installation
export PATH="$PWD/spot/local/bin:$PATH"
export LD_LIBRARY_PATH="$PWD/spot/local/lib:$LD_LIBRARY_PATH"

# Number of shards per combination
SHARDS_PER_COMBINATION=16

# Semantics (default to moore if not set)
SEMANTICS=${SEMANTICS:-"moore"}
NUM_USELESS_UNOBSERVABLES=${NUM_USELESS_UNOBSERVABLES:-0}

# Define all combinations
MODES_LONG=("lucas:belief-states" "lucas:projection-based" "lucas:mso" "christian:direct" "christian:belief" "christian:mso" "spot:ltlf" "spot:ltl" "spot:ltlfilt" "spot:ltlf-fo")

# Calculate combination and shard index
COMBINATION_ID=$(($SLURM_ARRAY_TASK_ID / $SHARDS_PER_COMBINATION))
SHARD_ID=$(($SLURM_ARRAY_TASK_ID % $SHARDS_PER_COMBINATION))

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
# Replace colon with underscore for the filename
SAFE_MODE=$(echo $MODE_LONG | tr ':' '_')

# Get the base Job ID (handles both array and non-array jobs)
BASE_JOB_ID=${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}
TASK_ID=${SLURM_ARRAY_TASK_ID:-0}

# Create directories and REDIRECT all output to the job-specific folder
mkdir -p "logs/${BASE_JOB_ID}" "results/${BASE_JOB_ID}/${SAFE_MODE}"
exec > "logs/${BASE_JOB_ID}/ltlf_po_${BASE_JOB_ID}_${TASK_ID}.out" 2>&1

OUTPUT_FILE="results/${BASE_JOB_ID}/${SAFE_MODE}/shard_${SHARD_ID}.csv"

echo "========================================="
echo "SLURM Job ID: $SLURM_JOB_ID"
echo "SLURM Array Job ID: ${SLURM_ARRAY_JOB_ID:-N/A}"
echo "Array Task ID: $SLURM_ARRAY_TASK_ID"
echo "Running on node: $(hostname)"
echo "Testing: $MODE_LONG"
echo "Semantics: $SEMANTICS"
echo "Shard: $SHARD_ID of $SHARDS_PER_COMBINATION"
echo "Output file: $OUTPUT_FILE"
echo "========================================="
echo ""

# Run the test
python3 runTests.py \
    --mode=$MODE_LONG \
    --test-dir=$TEST_DIR \
    --path=$SYFT_PATH \
    --timeout=$TIMEOUT \
    --output=$OUTPUT_FILE \
    --shard-id=$SHARD_ID \
    --num-shards=$SHARDS_PER_COMBINATION \
    --semantics=$SEMANTICS \
    --num-useless-unobservables=$NUM_USELESS_UNOBSERVABLES

EXIT_CODE=$?

echo ""
echo "========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Test completed successfully"
else
    echo "✗ Test failed with exit code: $EXIT_CODE"
fi
echo "========================================="

exit $EXIT_CODE
