#!/bin/bash
# Wildfire Simulator Performance Benchmark Script
# Compares sequential vs parallel execution with different thread counts

set -e

# Configuration
SIMULATOR="./cpp/build/wildfire_simulator"
CONFIG="data/sample/config_benchmark.json"
OUTPUT_FILE="benchmark_results.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Wildfire Simulator Benchmark Suite  ${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if simulator exists
if [ ! -f "$SIMULATOR" ]; then
    echo -e "${RED}Error: Simulator not found at $SIMULATOR${NC}"
    echo "Please build the simulator first:"
    echo "  cd cpp && mkdir -p build && cd build"
    echo "  cmake -DCMAKE_BUILD_TYPE=Release .."
    echo "  make -j\$(nproc)"
    exit 1
fi

# Check if config exists
if [ ! -f "$CONFIG" ]; then
    echo -e "${RED}Error: Config file not found at $CONFIG${NC}"
    exit 1
fi

# Detect available cores
CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
echo -e "${GREEN}Detected $CORES CPU cores${NC}\n"

# Clear old results
rm -f "$OUTPUT_FILE"
rm -f output/benchmark_*.json

# Thread counts to test
THREAD_COUNTS=(1 2 4 8)

# Filter thread counts based on available cores
FILTERED_THREADS=()
for t in "${THREAD_COUNTS[@]}"; do
    if [ "$t" -le "$CORES" ]; then
        FILTERED_THREADS+=("$t")
    fi
done

# Add max cores if not already included
if [ "$CORES" -gt 8 ] && [ "$CORES" -ne 16 ]; then
    FILTERED_THREADS+=("$CORES")
fi

echo -e "${YELLOW}Testing thread counts: ${FILTERED_THREADS[*]}${NC}\n"
echo "Thread Counts: ${FILTERED_THREADS[*]}" > "$OUTPUT_FILE"
echo "=====================================" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Store results for comparison
declare -a WALL_TIMES
declare -a SPEEDUPS

BASELINE_TIME=0

# Run benchmarks
for threads in "${FILTERED_THREADS[@]}"; do
    echo -e "${BLUE}Running with $threads thread(s)...${NC}"

    # Set OpenMP environment
    export OMP_NUM_THREADS=$threads
    export OMP_PROC_BIND=true
    export OMP_PLACES=cores

    # Run simulation
    START_TIME=$(date +%s.%N)
    $SIMULATOR $CONFIG > /dev/null 2>&1
    END_TIME=$(date +%s.%N)

    # Calculate wall time
    WALL_TIME=$(echo "$END_TIME - $START_TIME" | bc)
    WALL_TIMES+=("$WALL_TIME")

    # Read benchmark JSON if available
    BENCH_JSON="output/benchmark_99.json"
    if [ -f "$BENCH_JSON" ]; then
        # Extract metrics using Python or jq if available
        if command -v python3 &> /dev/null; then
            SIM_TIME=$(python3 -c "import json; print(json.load(open('$BENCH_JSON'))['simulated_time_minutes'])")
            BURNED=$(python3 -c "import json; print(json.load(open('$BENCH_JSON'))['cells_burned'])")
        else
            SIM_TIME="N/A"
            BURNED="N/A"
        fi
    else
        SIM_TIME="N/A"
        BURNED="N/A"
    fi

    # Calculate speedup
    if [ "$threads" -eq 1 ]; then
        BASELINE_TIME=$WALL_TIME
        SPEEDUP=1.00
    else
        SPEEDUP=$(echo "scale=2; $BASELINE_TIME / $WALL_TIME" | bc)
    fi
    SPEEDUPS+=("$SPEEDUP")

    # Calculate efficiency
    EFFICIENCY=$(echo "scale=2; ($SPEEDUP / $threads) * 100" | bc)

    # Print results
    echo -e "${GREEN}  Wall time: ${WALL_TIME}s${NC}"
    echo -e "${GREEN}  Speedup: ${SPEEDUP}x${NC}"
    echo -e "${GREEN}  Efficiency: ${EFFICIENCY}%${NC}"
    echo ""

    # Write to file
    echo "Threads: $threads" >> "$OUTPUT_FILE"
    echo "  Wall Time: ${WALL_TIME}s" >> "$OUTPUT_FILE"
    echo "  Speedup: ${SPEEDUP}x" >> "$OUTPUT_FILE"
    echo "  Efficiency: ${EFFICIENCY}%" >> "$OUTPUT_FILE"
    echo "  Simulated Time: ${SIM_TIME} min" >> "$OUTPUT_FILE"
    echo "  Cells Burned: $BURNED" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

    # Clean up for next run
    rm -f output/snapshot_99_*.json
done

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Benchmark Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

printf "%-10s %-15s %-12s %-12s\n" "Threads" "Wall Time (s)" "Speedup" "Efficiency"
printf "%-10s %-15s %-12s %-12s\n" "-------" "-------------" "-------" "----------"

for i in "${!FILTERED_THREADS[@]}"; do
    threads="${FILTERED_THREADS[$i]}"
    wall_time="${WALL_TIMES[$i]}"
    speedup="${SPEEDUPS[$i]}"
    efficiency=$(echo "scale=1; ($speedup / $threads) * 100" | bc)

    printf "%-10s %-15s %-12s %-12s\n" "$threads" "$wall_time" "${speedup}x" "${efficiency}%"
done

echo ""
echo -e "${GREEN}Results saved to: $OUTPUT_FILE${NC}"

# Calculate theoretical vs actual speedup
echo "" >> "$OUTPUT_FILE"
echo "=====================================" >> "$OUTPUT_FILE"
echo "Analysis:" >> "$OUTPUT_FILE"
echo "=====================================" >> "$OUTPUT_FILE"

BEST_SPEEDUP=${SPEEDUPS[-1]}
MAX_THREADS=${FILTERED_THREADS[-1]}

echo "Best speedup: ${BEST_SPEEDUP}x with $MAX_THREADS threads" >> "$OUTPUT_FILE"
echo "Amdahl's law prediction: Limited by sequential portions" >> "$OUTPUT_FILE"

# Calculate approximate parallel fraction
if command -v python3 &> /dev/null; then
    PARALLEL_FRACTION=$(python3 -c "
s = $BEST_SPEEDUP
n = $MAX_THREADS
# From Amdahl's law: S = 1 / (1-p + p/n)
# Solving for p: p = (n*s - n) / (s*n - s)
if s > 1:
    p = (n*s - n) / (s*n - s)
    print(f'{p:.3f}')
else:
    print('N/A')
")
    PARALLEL_PCT=$(echo "scale=1; $PARALLEL_FRACTION * 100" | bc)
    echo "Estimated parallel fraction: ${PARALLEL_FRACTION} (${PARALLEL_PCT}%)" >> "$OUTPUT_FILE"
fi

echo ""
echo -e "${YELLOW}Performance analysis complete!${NC}"
echo -e "View detailed results: ${GREEN}$OUTPUT_FILE${NC}"
