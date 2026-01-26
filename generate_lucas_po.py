import os
import subprocess
from pathlib import Path
import shutil
from concurrent.futures import ProcessPoolExecutor

def parse_part_file(file_path):
    inputs = []
    outputs = []
    unobservables = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('inputs'):
                inputs = line.split()[1:]
            elif line.startswith('outputs'):
                outputs = line.split()[1:]
            elif line.startswith('unobservables'):
                unobservables = line.split()[1:]
    return set(inputs), set(outputs), set(unobservables)

def generate_part_content(inputs, outputs, unobservables):
    content = []
    if inputs:
        content.append(f"inputs {' '.join(sorted(list(inputs)))}")
    if outputs:
        content.append(f"outputs {' '.join(sorted(list(outputs)))}")
    if unobservables:
        content.append(f"unobservables {' '.join(sorted(list(unobservables)))}")
    return "\n".join(content) + "\n"

def quantify_mona_content(original_content, unobservables):
    lines = original_content.splitlines()
    new_lines = []
    formula_started = False
    for line in lines:
        if line.strip().startswith('var2') and not formula_started:
            new_lines.append(line)
            if unobservables:
                quant_prefix = " ".join([f"all2 {var.upper()}:" for var in sorted(list(unobservables))])
                new_lines.append(f"{quant_prefix} (")
                formula_started = True
        elif line.strip() and not line.strip().startswith('#') and not line.strip().startswith('m2l-str') and not line.strip().startswith('var2'):
            new_lines.append(line)
        else:
            new_lines.append(line)
    
    if formula_started:
        last_line = new_lines[-1]
        if last_line.strip().endswith(';'):
            new_lines[-1] = last_line.rstrip(';') + ");"
        else:
            new_lines.append(");")
            
    return "\n".join(new_lines) + "\n"

def run_mona(mona_file, dfa_file):
    try:
        with open(dfa_file, 'w') as f:
            result = subprocess.run(['mona', '-u', '-xw', str(mona_file)], stdout=f, stderr=subprocess.PIPE, timeout=30)
        if result.returncode != 0:
            return f"Error running MONA on {mona_file}: {result.stderr.decode()}"
        return f"Successfully generated {dfa_file}"
    except subprocess.TimeoutExpired:
        return f"Timeout running MONA on {mona_file}"
    except Exception as e:
        return f"Exception running MONA on {mona_file}: {str(e)}"

def main():
    base_dir = Path("/home/cowclaw/ltlf-po-benchmarks/lucas")
    ltlf_base = base_dir / "ltlf"
    part_base = base_dir / "part"
    mso_base = base_dir / "mso"

    levels = ["0", "all"]
    mona_tasks = []

    for level_name in levels:
        new_part_dir = base_dir / f"po-part-{level_name}"
        new_mso_dir = base_dir / f"po-mso-{level_name}"
        os.makedirs(new_part_dir, exist_ok=True)
        os.makedirs(new_mso_dir, exist_ok=True)

        for ltlf_file in ltlf_base.rglob("*.ltlf"):
            rel_path = ltlf_file.relative_to(ltlf_base)
            file_stem = rel_path.stem
            sub_dir = rel_path.parent
            
            os.makedirs(new_part_dir / sub_dir, exist_ok=True)
            os.makedirs(new_mso_dir / sub_dir, exist_ok=True)

            part_file = part_base / sub_dir / f"{file_stem}.part"
            if not part_file.exists():
                continue

            inputs, outputs, unobservables = parse_part_file(part_file)
            env_vars = inputs.union(unobservables)

            if level_name == "0":
                new_inputs = env_vars
                new_unobs = set()
            else: # "all"
                new_inputs = set()
                new_unobs = env_vars

            new_part_content = generate_part_content(new_inputs, outputs, new_unobs)
            for ext in [".part", ".part.quant", ".part.rev.neg"]:
                with open(new_part_dir / sub_dir / f"{file_stem}{ext}", 'w') as f:
                    f.write(new_part_content)

            for mso_ext in [".mona", ".mona.rev", ".mona.rev.neg"]:
                orig_mona = mso_base / sub_dir / f"{file_stem}{mso_ext}"
                if orig_mona.exists():
                    target_mona = new_mso_dir / sub_dir / f"{file_stem}{mso_ext}"
                    shutil.copy(orig_mona, target_mona)
                    
                    target_dfa_ext = mso_ext.replace(".mona", ".dfa")
                    if not target_dfa_ext: target_dfa_ext = ".dfa"
                    target_dfa = new_mso_dir / sub_dir / f"{file_stem}{target_dfa_ext}"
                    
                    # Also handle .mona.quant separately
                    if mso_ext == ".mona":
                        quant_mona = new_mso_dir / sub_dir / f"{file_stem}.mona.quant"
                        if level_name == "all":
                            with open(orig_mona, 'r') as f:
                                orig_content = f.read()
                            with open(quant_mona, 'w') as f:
                                f.write(quantify_mona_content(orig_content, new_unobs))
                        else:
                            shutil.copy(orig_mona, quant_mona)
                        
                        mona_tasks.append((quant_mona, new_mso_dir / sub_dir / f"{file_stem}.dfa.quant"))
                    
                    mona_tasks.append((target_mona, target_dfa))

    print(f"Starting {len(mona_tasks)} MONA tasks...")
    # Parallel processing with limited workers to avoid overloading
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        futures = {executor.submit(run_mona, m, d): (m, d) for m, d in mona_tasks}
        for i, future in enumerate(futures):
            res = future.result()
            if i % 100 == 0:
                print(f"Processed {i}/{len(mona_tasks)} tasks...")
            if "Error" in res or "Timeout" in res:
                print(res)

if __name__ == "__main__":
    main()
