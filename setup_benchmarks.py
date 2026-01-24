import os
import subprocess
import random
import shutil
from pathlib import Path

benchmarks = [
    "SYNTCOMP-benchmarks/tlsf/ltl_f/generated_TLSF/workstation_resupply_pb_1_pe_.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl_f/generated_TLSF/workstation_resupply_pb_2_pe_.tlsf",
    "SYNTCOMP-benchmarks/tlsf/simple_arbiter/parametric/simple_arbiter.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba01.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba02.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba03.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba04.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba05.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba06.tlsf",
    "SYNTCOMP-benchmarks/tlsf/ltl2dba/non_parametric_from_acacia/ltl2dba07.tlsf"
]

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
