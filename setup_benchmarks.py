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
mso_dir = base_dir / "mso"
part_dir = base_dir / "part"

# Define levels of unobservability
levels = ["1-4", "1-2", "3-4", "all"]
po_dirs = {level: base_dir / f"po-part-{level}" for level in levels}

# Clean up and recreate directories
if base_dir.exists():
    shutil.rmtree(base_dir)

ltlf_dir.mkdir(parents=True, exist_ok=True)
mso_dir.mkdir(parents=True, exist_ok=True)
part_dir.mkdir(parents=True, exist_ok=True)
for d in po_dirs.values():
    d.mkdir(parents=True, exist_ok=True)

LTFL2FOL = "/home/cowclaw/lucas/Syft/build/bin/ltlf2fol"

def run_syfco(args):
    result = subprocess.run(["syfco"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

for tlsf_rel_path in benchmarks:
    tlsf_path = root_path / tlsf_rel_path
    if not tlsf_path.exists():
        continue
    
    stem = tlsf_path.stem
    ltlf_file = ltlf_dir / f"{stem}.ltlf"
    mso_file = mso_dir / f"{stem}.mona"
    part_file = part_dir / f"{stem}.part"
    
    print(f"Processing {stem}...")
    
    # Generate LTL formula (UNQUOTED for lucas/ltlf2fol)
    ltl_formula = run_syfco(["-f", "ltl", str(tlsf_path)])
    if not ltl_formula:
        ltl_formula = run_syfco(["-f", "lily", str(tlsf_path)])
        
    if ltl_formula:
        with open(ltlf_file, "w") as f:
            f.write(ltl_formula + "\n")
        
        # Generate MONA file for lucas
        try:
            with open(mso_file, "w") as f:
                subprocess.run([LTFL2FOL, "NNF", str(ltlf_file)], stdout=f, check=True)
        except Exception as e:
            print(f"Warning: Failed to generate MONA for {stem}: {e}")
            if mso_file.exists(): mso_file.unlink()
    else:
        print(f"Skipping {stem} due to conversion failure.")
        continue
    
    # Generate Part files
    inputs = run_syfco(["-ins", str(tlsf_path)])
    outputs = run_syfco(["-outs", str(tlsf_path)])
    
    if inputs is not None and outputs is not None:
        input_list = [i.strip(";,") for i in inputs.replace(",", " ").split() if i.strip(";,")]
        output_list = [o.strip(";,") for o in outputs.replace(",", " ").split() if o.strip(";,")]
        
        # FO (Full Observability)
        with open(part_file, "w") as f:
            f.write(f".inputs: {' '.join(input_list)}\n")
            f.write(f".outputs: {' '.join(output_list)}\n")
        
        if len(input_list) > 0:
            for level in levels:
                if level == "1-4": count = max(1, len(input_list) // 4)
                elif level == "1-2": count = max(1, len(input_list) // 2)
                elif level == "3-4": count = max(1, (3 * len(input_list)) // 4)
                elif level == "all": count = len(input_list)
                
                unobs = random.sample(input_list, count)
                remaining_inputs = [i for i in input_list if i not in unobs]
                
                po_file = po_dirs[level] / f"{stem}.part"
                with open(po_file, "w") as f:
                    if remaining_inputs:
                        f.write(f".inputs: {' '.join(remaining_inputs)}\n")
                    else:
                        f.write(".inputs:\n") # Empty inputs case
                    f.write(f".outputs: {' '.join(output_list)}\n")
                    if unobs:
                        f.write(f".unobservables: {' '.join(unobs)}\n")
        else:
            # If no inputs, all levels are the same as FO
            for level in levels:
                shutil.copy2(part_file, po_dirs[level] / f"{stem}.part")

print("Done.")
