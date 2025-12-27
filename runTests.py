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
        # Lucas version expects a MONA DFA file.
        dfa_file = input_file + ".dfa"
        if not os.path.exists(dfa_file):
            # 1. Parse .part file to keep variables from being optimized out by MONA
            vars_to_keep = []
            if os.path.exists(part_file):
                with open(part_file, 'r') as f:
                    for line in f:
                        if line.startswith('.') and ':' in line:
                            # Extract variable names from lines like .inputs: a b c
                            vars_to_keep.extend(line.split(':')[1].strip().split())

            # 2. Get the formulas
            with open(input_file, 'r') as f:
                formulas = [l.strip() for l in f if l.strip()]
            
            # Use 'tautology' as a way to ensure all variables are represented if a formula is empty or 'true'
            safe_true = get_safe_true(part_file)
            formulas = [f if f.lower() != "true" else safe_true for f in formulas]
            combined = " & ".join([f"({f})" for f in formulas])
            
            # 3. Use ltlf2fol to get MONA code
            bin_dir = self.path.parent
            ltlf2fol = bin_dir / "ltlf2fol"
            
            # ltlf2fol doesn't support stdin '-', so we write the combined formula to a temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ltlf', delete=True) as tf:
                tf.write(combined)
                tf.flush()
                mona_proc = subprocess.run([str(ltlf2fol), "NNF", tf.name], text=True, capture_output=True)
            
            mona_code = mona_proc.stdout
            if not mona_code:
                print(f"[{self.get_name()}] Error: ltlf2fol produced empty output. Stderr: {mona_proc.stderr}")
                return "" # This will cause an error downstream

            # 5. Run mona to get the DFA
            # MONA also doesn't support stdin '-', so we use a temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.mona', delete=True) as tf_mona:
                tf_mona.write(mona_code)
                tf_mona.flush()
                mona_out = subprocess.run(["mona", "-u", "-xw", tf_mona.name], text=True, capture_output=True)
            
            with open(dfa_file, 'w') as f:
                f.write(mona_out.stdout)

        mapping = {
            "direct": "partial dfa",
            "belief": "partial cordfa",
            "mso": "partial dfa"
        }
        lucas_mode = mapping.get(mode, "partial dfa")
        return f'"{self.path}" {dfa_file} {part_file} 0 {lucas_mode}'

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

def get_variables_from_part(part_file):
    vars = []
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                if line.startswith('.') and ':' in line:
                    vars.extend(line.split(':')[1].strip().split())
    # Standardize names (remove commas, whitespace)
    return sorted(list(set(v.strip().replace(',', '') for v in vars if v.strip())))

def get_safe_true(part_file):
    vars = get_variables_from_part(part_file)
    if not vars:
        return "true"
    # Construct a tautology that mentions every variable to prevent them from being optimized out
    return " & ".join([f"({v} | !{v})" for v in vars])

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

    return tests

def executeTest(test, mode, timeout, solver, disregard, iter):
    # Create a unique temporary directory
    temp_dir = tempfile.mkdtemp()
    
    # Get the original filenames
    file1_name = os.path.basename(test[0])
    file2_name = os.path.basename(test[1])

    inputfile = os.path.join(temp_dir, file1_name)
    partfile = os.path.join(temp_dir, file2_name)

    # Copy files to the unique temporary directory
    shutil.copy2(test[0], inputfile)
    shutil.copy2(test[1], partfile)
    
    # If we are NOT disregarding anything, we can copy the existing DFA
    # If we ARE disregarding, the DFA must be regenerated inside LucasSyftSolver
    if not disregard:
        dfa_orig = str(test[0]) + ".dfa"
        if os.path.exists(dfa_orig):
            shutil.copy2(dfa_orig, inputfile + ".dfa")

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
            if name_prefix.lower() == "lucas":
                solvers.append(LucasSyftSolver(path, name=name_prefix))
            elif name_prefix.lower() == "christian":
                solvers.append(SyftSolver(path, name=name_prefix))
            else:
                solvers.append(SyftSolver(path, name=name_prefix))
        else:
            solvers.append(SyftSolver(s_entry))

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

    