from pathlib import Path
import subprocess
import os
import re
import shutil
import sys
import csv 
import time 
import tempfile
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import defaultdict

class Solver():
    def __init__(self, path, name=None):
        self.path = Path(path).expanduser().resolve()
        self.name = name if name else str(self.path)

    def get_command(self, input_file, part_file, mode):
        """Returns the command string to execute."""
        raise NotImplementedError

    def parse_output(self, output_bytes):
        """Returns (result_code, time_ms) from tool output. result: 1=Realizable, 0=Unrealizable"""
        raise NotImplementedError

    def get_name(self):
        return self.name

class SyftSolver(Solver):
    def get_command(self, input_file, part_file, mode):
        return f'"{self.path}" {input_file} {part_file} 0 {mode}'

    def parse_output(self, output_bytes):
        l_str = str(output_bytes)
        lines = l_str.split("\\n")
        # Try to find the time in output 
        try:
            rr = re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", lines[-2])
            assert(len(rr) == 1)
            time_ms = float(rr[0])
        except Exception:
            # Fallback for if output structure differs
            time_ms = 0.0
        
        result = None 
        if "Unrealizable" in l_str:
            result = 0
        if "Realizable" in l_str:
            result = 1
        return result, time_ms

class LucasSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode):
        # Configuration based on lucas-benchmarks-instructions.txt:
        # direct (Belief-states): partial dfa, uses .dfa, .part
        # belief (Projection-based): partial cordfa, uses .dfa.rev.neg, .part.rev.neg
        # mso (MSO): full dfa, uses .dfa.quant, .part.quant
        config = {
            "direct": ("partial", "dfa", ".dfa", ""),
            "belief": ("partial", "cordfa", ".dfa.rev.neg", ".rev.neg"),
            "mso":    ("full",    "dfa", ".dfa.quant",   ".quant")
        }
        
        obs, inp_type, dfa_suffix, part_suffix = config.get(mode, ("partial", "dfa", ".dfa", ""))
        
        dfa_file = input_file + dfa_suffix
        actual_part_file = part_file + part_suffix
        
        # Check if actual_part_file exists, else use base part_file
        if not os.path.exists(actual_part_file):
            actual_part_file = part_file

        if not os.path.exists(dfa_file):
            # Try to find a source MONA file to generate the DFA
            # For .dfa, look for .mona; for .dfa.quant, look for .mona.quant; for .dfa.rev.neg, look for .mona.rev.neg
            mona_source_suffix = dfa_suffix.replace(".dfa", ".mona")
            stem = Path(input_file).stem
            mona_source = os.path.join(os.path.dirname(input_file), stem + mona_source_suffix)
            
            if os.path.exists(mona_source):
                # Run MONA on the source file to get the DFA
                mona_out = subprocess.run(["mona", "-u", "-xw", mona_source], text=True, capture_output=True)
                with open(dfa_file, 'w') as f:
                    f.write(mona_out.stdout)
            elif dfa_suffix == ".dfa":
                # Use normalized formula already written to input_file
                with open(input_file, 'r') as f:
                    final_formula = f.read().strip()
                
                ltlf2fol = self.path.parent / "ltlf2fol"
                with tempfile.NamedTemporaryFile(mode='w', suffix='.ltlf', delete=True) as tf:
                    tf.write(final_formula)
                    tf.flush()
                    mona_proc = subprocess.run([str(ltlf2fol), "NNF", tf.name], text=True, capture_output=True)
                
                mona_code = mona_proc.stdout
                if not mona_code:
                    print(f"[{self.get_name()}] Error: ltlf2fol produced empty output. Stderr: {mona_proc.stderr}")
                    return ""
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.mona', delete=True) as tf_mona:
                    tf_mona.write(mona_code)
                    tf_mona.flush()
                    mona_out = subprocess.run(["mona", "-u", "-xw", tf_mona.name], text=True, capture_output=True)
                
                with open(dfa_file, 'w') as f:
                    f.write(mona_out.stdout)
            else:
                print(f"[{self.get_name()}] Error: {dfa_file} not found and no source {mona_source} to generate it.")
                return ""

        return f'"{self.path}" {dfa_file} {actual_part_file} 0 {obs} {inp_type}'

    def parse_output(self, output_bytes):
        # Reuse logic or customize if lucas output differs significantly
        l_str = str(output_bytes)
        result = None 
        if "unrealizable" in l_str: result = 0
        elif "realizable" in l_str: result = 1
        
        # Lucas Syft often prints time in ms at the end
        lines = l_str.strip().split("\\n")
        time_ms = 0.0
        for line in reversed(lines):
            rr = re.findall(r"(\d+\.?\d*)\s*ms", line)
            if rr:
                time_ms = float(rr[0])
                break
        return result, time_ms

def normalize_part_file(filename):
    """
    Ensures the part file has the format:
    .inputs: var1 var2
    .outputs: var3 var4
    ...
    Also lowercases variable names and ensures all unobservables are also inputs.
    """
    if not os.path.exists(filename):
        return
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    inputs = set()
    outputs = set()
    unobs = set()
    
    for line in lines:
        line = line.strip().lower()
        if not line: continue
        
        parts = []
        if line.startswith('.'):
            key_part, vars_part = line.split(':', 1)
            key = key_part.strip().lstrip('.')
            vars_str = vars_part
        else:
            parts = line.split()
            if not parts: continue
            key = parts[0].replace(":", "")
            vars_str = " ".join(parts[1:])
        
        vars_list = [v.strip().replace(",", "") for v in vars_str.replace(",", " ").split() if v.strip()]
        if key in ['inputs', 'input']: inputs.update(vars_list)
        elif key in ['outputs', 'output']: outputs.update(vars_list)
        elif key in ['unobservables', 'unobservable']: unobs.update(vars_list)

    # All unobservables must be inputs in Partial Observability
    inputs.update(unobs)
    
    with open(filename, 'w') as f:
        f.write(f".inputs: {' '.join(sorted(list(inputs)))}\n")
        f.write(f".outputs: {' '.join(sorted(list(outputs)))}\n")
        if unobs:
            f.write(f".unobservables: {' '.join(sorted(list(unobs)))}\n")

def get_variables_from_part(part_file):
    vars = set()
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                line = line.strip().lower()
                if line.startswith('.') and ':' in line:
                    vars.update(line.split(':')[1].strip().split())
                elif any(line.startswith(k) for k in ['inputs', 'outputs', 'unobservables']):
                    parts = line.split()
                    if len(parts) > 1:
                        vars.update(parts[1:])
    return sorted(list(vars))

def get_safe_true(part_file):
    vars = get_variables_from_part(part_file)
    if not vars:
        return ["true"]
    # Return a list of tautologies, one for each variable
    return [f"{v} | ~{v}" for v in vars]

def get_normalized_formula(formula_str, vars_list=None):
    # Lowercase variables
    f = formula_str.lower()
    # Standardize operators
    f = f.replace("&&", "&").replace("||", "|").replace("!", "~").replace("next", "X").replace("always", "G").replace("eventually", "F").replace("until", "U")
    # Some versions of ltlf2fol might use -> or <-> 
    # but we ensure spaces around them for safety
    f = f.replace("<->", " <-> ").replace("->", " -> ")
    
    # Replace true/false literals with tautologies/contradictions if we have variables
    # because some versions of ltlf2fol fail on 'true'/'false' when a part file is used.
    if vars_list:
        v = vars_list[0]
        f = f.replace(" true ", f" ({v} | ~{v}) ").replace("(true)", f"({v} | ~{v})")
        f = f.replace(" false ", f" ({v} & ~{v}) ").replace("(false)", f"({v} & ~{v})")
        if f.strip() == "true": f = f"({v} | ~{v})"
        if f.strip() == "false": f = f"({v} & ~{v})"
    
    # Clean up spaces
    f = " ".join(f.split())
    return f

class Statistics():
    def __init__(self):
        self.stats = defaultdict(lambda: {'passed': 0, 'failed': 0, 'timeout': 0, 'other': 0})
        self.results = defaultdict(dict) # test_path -> {impl: (time, status)}
        self.lock = threading.Lock()
        self.solver_locks = defaultdict(threading.Lock)

    def add_result(self, test_path, impl, time, status, outcome):
        with self.lock:
            self.results[test_path][impl] = (time, status)
            if outcome == 'passed': self.stats[impl]['passed'] += 1
            elif outcome == 'failed': self.stats[impl]['failed'] += 1
            elif outcome == 'timeout': self.stats[impl]['timeout'] += 1
            elif outcome == 'other': self.stats[impl]['other'] += 1

# for statistics 
statistics = Statistics()

def replace_line_in_file(filename, line_number, new_line):
    """
        Replaces a line in a file.
    """
    with open(filename, 'r') as file:
        lines = file.readlines()

    if line_number < 1 or line_number > len(lines):
        raise IndexError("Line number out of range")
    lines[line_number - 1] = new_line + '\n'
    with open(filename, 'w') as file:
        file.writelines(lines)


def collectTests(testdir):
    global statistics
    p = Path(testdir)
    tests = []
    for file in p.rglob("*/*.ltlf"):
        # Check for corresponding .part 
        corresponding_partfile = file.with_suffix(".part")
        corresponding_output = file.with_name("expected.txt")
        if (not corresponding_partfile.is_file()) or (not corresponding_output.is_file()):
            print('One of the tests is missing the correct files')
            if not corresponding_partfile.is_file():
                print('Expected to find ' + str(corresponding_partfile))
            if not corresponding_output.is_file():
                print('Expected to find ' + str(corresponding_output))
            sys.exit(-1)
        # Read the expected file and save this information about the test
        expected_res = None
        with open(corresponding_output, "r") as f:
            try:
                expected_res = int(f.read())
            except Exception:
                print("Expected to find 0 / 1 in {str(corresponding_output)}")
                sys.exit(-1)
        tests.append((file, corresponding_partfile, expected_res))

    # If no tests found with .part files in same dir, try looking for lucas-style structure
    if not tests:
        for file in p.rglob("*.ltlf"):
            # Look for .part in ../part/
            stem = file.stem
            part_path = file.parent.parent / "part" / (stem + ".part")
            if part_path.exists():
                # For Lucas tests, we might not have expected.txt, so we use None or 1 as default
                expected_txt = file.parent / "expected.txt"
                expected_res = 1 # Default to realizable if unknown
                if expected_txt.exists():
                    with open(expected_txt, 'r') as f:
                        try: expected_res = int(f.read().strip())
                        except: pass
                tests.append((file, part_path, expected_res))

    return tests

def executeTest(test, mode, timeout, solver, disregard, iter):
    # Create a unique temporary directory
    temp_dir = tempfile.mkdtemp()
    
    # Get the original filenames
    file1_name = os.path.basename(test[0])
    file2_name = os.path.basename(test[1])

    inputfile = os.path.join(temp_dir, file1_name)
    partfile = os.path.join(temp_dir, file2_name)

    # Determine which part file to use: check for solver-specific one first
    original_part = test[1]
    solver_name = solver.get_name().lower()
    
    # Try: stem.solver_name.part (e.g., bench.christian.part)
    potential_specific_part = original_part.parent / (original_part.stem + "." + solver_name + original_part.suffix)
    if not potential_specific_part.exists():
        # Try: filename.solver_name (e.g., bench.part.christian)
        potential_specific_part = original_part.parent / (original_part.name + "." + solver_name)
    
    if potential_specific_part.exists():
        actual_source_part = potential_specific_part
    else:
        actual_source_part = original_part

    # Initialize partition file by copying selected source
    shutil.copy2(actual_source_part, partfile)

    # Normalize both files for maximum compatibility
    normalize_part_file(partfile)
    
    with open(test[0], 'r') as f:
        lines = [l.strip() for l in f if l.strip()]
    
    # For Christian's solver, we need main/backup format (at least 2 lines)
    # If there's only one line in a Lucas benchmark, duplicate it.
    if "christian" in solver.get_name().lower() and len(lines) == 1:
        lines = [lines[0], lines[0]]

    # Combine lines: put each formula on a separate line
    # The Christian ltlf2fol is very sensitive and often expects this multi-line format
    all_vars = get_variables_from_part(partfile)
    safe_tautologies = [f"{v} | ~{v}" for v in all_vars]
    normalized_formulas = [get_normalized_formula(l, all_vars) for l in lines]
    
    final_lines = normalized_formulas + safe_tautologies
        
    with open(inputfile, 'w') as f:
        for line in final_lines:
            f.write(line + "\n")
    
    # If we are NOT disregarding anything, we can copy the existing DFA and variants
    if not disregard:
        for suffix in [".dfa", ".dfa.rev.neg", ".dfa.quant"]:
            src = str(test[0]) + suffix
            if os.path.exists(src):
                shutil.copy2(src, inputfile + suffix)
            # Try to find MONA source files as well (e.g. from a sibling 'mso' directory)
            stem = Path(test[0]).stem
            parent = Path(test[0]).parent
            mona_suffixes = [".mona", ".mona.rev.neg", ".mona.quant"]
            for ms in mona_suffixes:
                m_src = parent / (stem + ms)
                if m_src.exists():
                    shutil.copy2(m_src, os.path.join(temp_dir, stem + ms))
                # Also check sibling 'mso' directory
                m_src_alt = parent.parent / "mso" / (stem + ms)
                if m_src_alt.exists():
                    shutil.copy2(m_src_alt, os.path.join(temp_dir, stem + ms))

    # Copy part variants if they exist
    for suffix in [".rev.neg", ".quant"]:
        src = str(actual_source_part) + suffix
        if os.path.exists(src):
            shutil.copy2(src, partfile + suffix)

    # Depending on the disregard argument, replace either first or second line in file with a safe tautology
    if disregard:
        safe_true = get_safe_true(partfile)
        if disregard == "main":
            replace_line_in_file(inputfile, 1, safe_true)
        elif disregard == "backup":
            replace_line_in_file(inputfile, 2, safe_true) 
    results = []
    times   = []
    solver_name = solver.get_name()
    for i in range(iter):
        command = solver.get_command(inputfile, partfile, mode)
        try:
            print(f"[{solver_name}] {command}")
            # Use a lock for this specific solver to prevent parallel executions from colliding on temp files
            with statistics.solver_locks[solver.path.parent]:
                completed_proc = subprocess.run(
                    command,
                    timeout=timeout,
                    cwd=solver.path.parent,
                    shell=True,
                    capture_output=True
                )
            
            output = completed_proc.stdout
            error_output = completed_proc.stderr
            full_log = output + (b"\n" if output and error_output else b"") + error_output

            # If a log directory is provided, save the output
            if getattr(args, 'logdir', None):
                log_name = f"{Path(test[0]).stem}_{solver_name}_iter{i}.log"
                log_path = Path(args.logdir) / log_name
                log_path.write_bytes(full_log)

            if completed_proc.returncode != 0:
                print(f"[{solver_name}] Command failed with exit code {completed_proc.returncode}")
                if error_output:
                    print(f"[{solver_name}] Stderr: {error_output.decode(errors='replace')}")
                statistics.add_result(str(test[0]), solver_name, -1, f"error({completed_proc.returncode})", "other")
                shutil.rmtree(temp_dir)
                return
            
            result, time_ms = solver.parse_output(output)
            results.append(result)
            times.append(time_ms)
        except subprocess.TimeoutExpired as e:
            # Try to capture whatever output was there before timeout if possible (not always available in TimeoutExpired)
            statistics.add_result(str(test[0]), solver_name, -1, "timeout", "timeout")
            shutil.rmtree(temp_dir)
            return
        except Exception as e:
            print(f"[{solver_name}] Unexpected error: {e}")
            statistics.add_result(str(test[0]), solver_name, -1, "exception", "other")
            shutil.rmtree(temp_dir)
            return

    # Cleanup temp dir
    shutil.rmtree(temp_dir)

    # Check that all results are identical 
    if not all(elem == results[0] for elem in results):
        statistics.add_result(str(test[0]), solver_name, -1, "rnid", "other")
        return 
    
    average_time = sum(times) / len(times)
    if not disregard and results[0] != test[2]: # If we disregard smth, realizability possibilities change!
        statistics.add_result(str(test[0]), solver_name, average_time / 1000, "WA", "failed")
    else:
        statistics.add_result(str(test[0]), solver_name, average_time / 1000, "", "passed")
                



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-impl',
                        choices=['direct', 'belief', 'mso'],
                        default='direct',
                        help='Select which implementation to run the tests with')
    parser.add_argument('-disregard', default=None, choices=[None, "backup", "main"])
    parser.add_argument('-o',
                        help="Specify the result file",
                        default=None)
    parser.add_argument('-tdir',
                        help="Specify the directory where tests are stord",
                        default="christian/tests2/")
    parser.add_argument('-syft',
                        help="Specify the path to Syft executable(s)",
                        default=["lucas:~/lucas/Syft/build/bin/Syft", "christian:~/christian/ltlf-synth-unrel-input-aaai2025/Syft/build/bin/Syft"],
                        nargs='+')
    #parser.add_argument('-test', help="Specify which test to run", default=None)
    parser.add_argument('-j', type=int,
                        help="Number of threads to use (t >= 1 --> mutithreading)",
                        default=None)
    parser.add_argument('-timeout',
                        help="The timeout to use",
                        default=1500)
    parser.add_argument('-iter',
                        help="How often to run each test for better comparability",
                        default=1, type=int)
    parser.add_argument('-logdir',
                        help="Directory to save test outputs",
                        default=None)

    args = parser.parse_args()
    
    if args.logdir:
        Path(args.logdir).mkdir(parents=True, exist_ok=True)

    print("Collecting tests")
    tests = collectTests(args.tdir)

    solvers = []
    for s_entry in args.syft:
        if ":" in s_entry:
            name_prefix, path = s_entry.split(":", 1)
            # Tilde expansion and resolve
            path = os.path.expanduser(path)
            s_path = Path(path).resolve()
            if not s_path.exists():
                print(f"Warning: Solver '{name_prefix}' executable not found at {s_path}. Skipping.")
                continue
            
            if name_prefix.lower() == "lucas":
                solvers.append(LucasSyftSolver(str(s_path), name=name_prefix))
            else:
                solvers.append(SyftSolver(str(s_path), name=name_prefix))
        else:
            path = os.path.expanduser(s_entry)
            s_path = Path(path).resolve()
            if not s_path.exists():
                print(f"Warning: Solver executable not found at {s_path}. Skipping.")
                continue
            solvers.append(SyftSolver(str(s_path)))

    if not solvers:
        print("Error: No valid solvers found. Exiting.")
        sys.exit(-1)

    # Create csvwriter + lock for output file + write initial row
    max_workers = args.j if args.j else None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for test in tests:
            for solver in solvers:
                futures.append(executor.submit(executeTest, test, args.impl, args.timeout, solver, args.disregard, args.iter))

        for future in as_completed(futures):
            future.result()  # Wait for all futures to complete


    # Timeout (1) / Unexpected Output (2) / Failure (3), 
    print("================================")
    print("========= STATISTICS ===========")
    for solver in solvers:
        name = solver.get_name()
        print(f"--- Statistics for {name} ---")
        print(f"SUCCESS: {statistics.stats[name]['passed']}")
        print(f"FAILED: {statistics.stats[name]['failed']}")
        print(f"TIMEOUT: {statistics.stats[name]['timeout']}")
        print(f"ERROR: {statistics.stats[name]['other']}")

    if not args.o:
        args.o = f"results-{args.impl}.csv"

    header = ["Test"]
    for solver in solvers:
        name = solver.get_name()
        header.extend([f"{name}_Time", f"{name}_Status"])
    
    rows = [header]
    for test_path in sorted(statistics.results.keys()):
        row = [test_path]
        for solver in solvers:
            name = solver.get_name()
            res = statistics.results[test_path].get(name, ("N/A", "N/A"))
            row.extend([res[0], res[1]])
        rows.append(row)

    with open(args.o, 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)

    