#!/bin/bash
#SBATCH --job-name=syft_test_all
#SBATCH --output=logs/test_all_%A_%a.out
#SBATCH --error=logs/test_all_%A_%a.err
#SBATCH --array=0-95
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=12:00:00
#SBATCH --exclude=cn[31-44],gpu[1-4],gpu[6-8]

# Create logs directory if it doesn't exist
mkdir -p logs results

# Configuration
TIMEOUT=180
TEST_DIR="lucas"
LUCAS_PATH="~/work/lucas/Syft/build/bin/Syft"
CHRISTIAN_PATH="~/work/ltlf-synth-unrel-input-aaai2025/Syft/build/bin/Syft"

# Number of shards per combination
SHARDS_PER_COMBINATION=16

# Define all combinations
SOLVERS=("lucas" "lucas" "lucas" "christian" "christian" "christian")
MODES=("direct" "belief" "mso" "direct" "belief" "mso")

# Calculate combination and shard index
COMBINATION_ID=$(($SLURM_ARRAY_TASK_ID / $SHARDS_PER_COMBINATION))
SHARD_ID=$(($SLURM_ARRAY_TASK_ID % $SHARDS_PER_COMBINATION))

SOLVER=${SOLVERS[$COMBINATION_ID]}
MODE=${MODES[$COMBINATION_ID]}

# Set the correct path based on solver
if [ "$SOLVER" = "lucas" ]; then
    SYFT_PATH=$LUCAS_PATH
else
    SYFT_PATH=$CHRISTIAN_PATH
fi

# Unique output file per shard
OUTPUT_FILE="results/test_${SOLVER}_${MODE}_shard_${SHARD_ID}.csv"

echo "========================================="
echo "SLURM Job ID: $SLURM_JOB_ID"
echo "Array Task ID: $SLURM_ARRAY_TASK_ID"
echo "Running on node: $(hostname)"
echo "Testing: $SOLVER solver with $MODE mode"
echo "Shard: $SHARD_ID of $SHARDS_PER_COMBINATION"
echo "Output file: $OUTPUT_FILE"
echo "========================================="
echo ""

# Run the test
python3 runTests.py \
    --solver=$SOLVER \
    --mode=$MODE \
    --test-dir=$TEST_DIR \
    --path=$SYFT_PATH \
    --timeout=$TIMEOUT \
    --output=$OUTPUT_FILE \
    --shard-id=$SHARD_ID \
    --num-shards=$SHARDS_PER_COMBINATION

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
