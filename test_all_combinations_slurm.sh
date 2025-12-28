#!/bin/bash
#SBATCH --job-name=syft_test_all
#SBATCH --output=logs/test_all_%A_%a.out
#SBATCH --error=logs/test_all_%A_%a.err
#SBATCH --array=0-5
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --partition=batch
#SBATCH --exclude=gpu1,gpu2,gpu3,gpu7,gpu8,cn31,cn32,cn33,cn34,cn35,cn36,cn37,cn38,cn39,cn40,cn41,cn42,cn43,cn44

# Create logs directory if it doesn't exist
mkdir -p logs

# Configuration
TIMEOUT=60
TEST_DIR="lucas"
LUCAS_PATH="~/work/lucas/Syft/build/bin/Syft"
CHRISTIAN_PATH="~/work/ltlf-synth-unrel-input-aaai2025/Syft/build/bin/Syft"

# Define all combinations
# Array index maps to: solver_mode combination
SOLVERS=("lucas" "lucas" "lucas" "christian" "christian" "christian")
MODES=("direct" "belief" "mso" "direct" "belief" "mso")

# Get the combination for this array task
SOLVER=${SOLVERS[$SLURM_ARRAY_TASK_ID]}
MODE=${MODES[$SLURM_ARRAY_TASK_ID]}

# Set the correct path based on solver
if [ "$SOLVER" = "lucas" ]; then
    SYFT_PATH=$LUCAS_PATH
else
    SYFT_PATH=$CHRISTIAN_PATH
fi

OUTPUT_FILE="results/test_${SOLVER}_${MODE}.csv"
mkdir -p results

echo "========================================="
echo "SLURM Job ID: $SLURM_JOB_ID"
echo "Array Task ID: $SLURM_ARRAY_TASK_ID"
echo "Running on node: $(hostname)"
echo "Testing: $SOLVER solver with $MODE mode"
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
    --output=$OUTPUT_FILE

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
