import os
from pathlib import Path

def parse_unobs_from_part(file_path):
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith('unobservables'):
                return set(line.strip().split()[1:])
    return set()

def main():
    base_dir = Path("/home/cowclaw/ltlf-po-benchmarks/ltlf-fin-benchmarks")
    if not base_dir.exists():
        print(f"Error: {base_dir} not found.")
        return

    # Check level 'all'
    po_all_dir = base_dir / "po-part-all"
    if po_all_dir.exists():
        print(f"Checking {po_all_dir}...")
        for part_file in po_all_dir.glob("*.part"):
            unobs = parse_unobs_from_part(part_file)
            # Should match total inputs? 
            # In setup_benchmarks.py, 'all' level chooses all inputs by definition.
            print(f"  {part_file.name}: {len(unobs)} unobservables")
    else:
        print("Warning: po-part-all not found.")

    # Check level '1-2' samples
    benchmark_samples = {} # stem -> list of unobs sets
    
    sample_dirs = sorted(list(base_dir.glob("po-part-1-2_*")))
    print(f"Found {len(sample_dirs)} sample directories for level 1-2.")
    
    for s_dir in sample_dirs:
        for part_file in s_dir.glob("*.part"):
            stem = part_file.stem
            unobs = parse_unobs_from_part(part_file)
            if stem not in benchmark_samples:
                benchmark_samples[stem] = []
            
            # Check for duplicates
            if unobs in benchmark_samples[stem]:
                print(f"ERROR: Duplicate sample for {stem} found in {s_dir.name}")
            else:
                benchmark_samples[stem].append(unobs)

    # Summary
    print("\nBenchmark Sample Counts (Unique):")
    for stem, samples in sorted(benchmark_samples.items()):
        if len(samples) < len(sample_dirs):
            print(f"  {stem:40}: {len(samples)} samples (out of {len(sample_dirs)})")
        # else:
            # print(f"  {stem:40}: {len(samples)} (Full)")

    print("\nVerification complete.")

if __name__ == "__main__":
    main()
