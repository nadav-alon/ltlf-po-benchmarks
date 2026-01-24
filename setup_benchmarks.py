import os
import subprocess
import random
import shutil
from pathlib import Path

import glob

categories = {
    "ltl_f": 100, # mostly small
    "amba": 30,
    "ltl2dba": 50,
    "arbiters_zoo": 50,
    "generalized_buffer": 20,
    "load_balancer": 20,
    "lift": 20,
    "lily": 50,
    "robot_grid": 20,
    "prioritized_arbiter": 20,
    "simple_arbiter": 20,
    "tsl_smart_home_jarvis": 50,
    "collector": 20,
    "mux": 10
}

benchmarks = []
root_path = Path("/home/cowclaw/ltlf-po-benchmarks")
for category, limit in categories.items():
    tlsf_files = list(root_path.glob(f"SYNTCOMP-benchmarks/tlsf/{category}/**/*.tlsf"))
    # Filter out unrealizable if they are in specific folders that separate them
    tlsf_files = [f for f in tlsf_files if "unreal" not in str(f).lower()]
    
    # Take a sample if there are too many
    if len(tlsf_files) > limit:
        tlsf_files = random.sample(tlsf_files, limit)
    
    for f in tlsf_files:
        benchmarks.append(str(f.relative_to(root_path)))

print(f"Collected {len(benchmarks)} benchmarks total.")

base_dir = Path("/home/cowclaw/ltlf-po-benchmarks/full-observability")
ltlf_dir = base_dir / "ltlf"
part_dir = base_dir / "part"
po_part_dir = base_dir / "po-part"

# Clean up before re-generating
if base_dir.exists():
    shutil.rmtree(base_dir)

ltlf_dir.mkdir(parents=True, exist_ok=True)
part_dir.mkdir(parents=True, exist_ok=True)
po_part_dir.mkdir(parents=True, exist_ok=True)

def run_syfco(args):
    result = subprocess.run(["syfco"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

for tlsf_rel_path in benchmarks:
    tlsf_path = Path("/home/cowclaw/ltlf-po-benchmarks") / tlsf_rel_path
    if not tlsf_path.exists():
        print(f"Skipping {tlsf_rel_path} - not found.")
        continue
    
    stem = tlsf_path.stem
    ltlf_file = ltlf_dir / f"{stem}.ltlf"
    part_file = part_dir / f"{stem}.part"
    po_part_file = po_part_dir / f"{stem}.part"
    
    print(f"Processing {stem}...")
    
    # Generate LTL formula (quoted)
    ltl_formula = run_syfco(["-f", "ltl", "--quote", "double", str(tlsf_path)])
    if not ltl_formula:
        ltl_formula = run_syfco(["-f", "lily", "--quote", "double", str(tlsf_path)])
        
    if ltl_formula:
        with open(ltlf_file, "w") as f:
            f.write(ltl_formula + "\n")
    else:
        print(f"Skipping {stem} due to conversion failure.")
        continue
    
    # Generate Part file (unquoted)
    inputs = run_syfco(["-ins", str(tlsf_path)])
    outputs = run_syfco(["-outs", str(tlsf_path)])
    
    if inputs is not None and outputs is not None:
        input_list = [i.strip(";,") for i in inputs.replace(",", " ").split() if i.strip(";,")]
        output_list = [o.strip(";,") for o in outputs.replace(",", " ").split() if o.strip(";,")]
        
        with open(part_file, "w") as f:
            f.write(f".inputs: {' '.join(input_list)}\n")
            f.write(f".outputs: {' '.join(output_list)}\n")
        
        # Generate PO Part file (1/4 of inputs unobservable)
        if len(input_list) > 0:
            num_unobs = max(1, len(input_list) // 4)
            unobs = random.sample(input_list, num_unobs)
            remaining_inputs = [i for i in input_list if i not in unobs]
            
            with open(po_part_file, "w") as f:
                f.write(f".inputs: {' '.join(remaining_inputs)}\n")
                f.write(f".outputs: {' '.join(output_list)}\n")
                f.write(f".unobservables: {' '.join(unobs)}\n")
        else:
            shutil.copy2(part_file, po_part_file)

print("Done.")
