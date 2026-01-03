import subprocess
import os
import sys
import re
import csv 
from pathlib import Path
import time 
import tempfile
import argparse
import threading
import shutil


class Solver():
    def __init__(self, path, name=None):
        self.path = Path(path).expanduser().resolve()
        self.name = name if name else str(self.path)

    def get_command(self, input_file, part_file, mode)-> str:
        """Returns the command string to execute.

        Args:
            input_file (str): The input file path.
            part_file (str): The part file path.
            mode (str): The mode.
        Returns:
            str: The command string to execute.
        """
        raise NotImplementedError

    def parse_output(self, output_bytes)-> (int, float):
        """Returns (result_code, time_ms) from tool output. result: 1=Realizable, 0=Unrealizable"""
        raise NotImplementedError

    def get_name(self)-> str:
        return self.name


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
        return "true"
    # Return a list of tautologies, one for each variable
    return " && ".join([f"{v} | ~{v}" for v in vars])

class ChristianSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode)-> str:
        # Christian's Syft expects .main and .backup files
        # and handles ltlf2fol conversion internally
        
        if not part_file.endswith('.christian.part'):
            christian_part = part_file + '.christian.part'
            if not os.path.exists(christian_part):
                with open(part_file, 'r') as f:
                    content = f.read()
                with open(christian_part, 'w') as f:
                    f.write(content.replace('inputs:', '.inputs:').replace('outputs:', '.outputs:'))
            part_file = christian_part

        if not input_file.endswith('christian.ltlf'):
            christian_input = input_file + '.christian.ltlf'
            if not os.path.exists(christian_input):
                with open(input_file, 'r') as f:
                    content = f.read().strip()
                
                # Christian's Syft expects the .ltlf file to have exactly 2 lines:
                # Line 1: main formula
                # Line 2: backup formula (tautology)
                safe_true = get_safe_true(part_file)
                
                with open(christian_input, 'w') as f:
                    f.write(content + '\n')
                    f.write(safe_true + '\n')
                    
            input_file = christian_input
        
        # Christian's Syft takes the .ltlf file and handles conversion internally
        return f'"{self.path}" {input_file} {part_file} 0 {mode}'

    def parse_output(self, output_bytes)-> (int, float):
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

        # if result == 1:
            # TODO: need to save the output of the tool

        return result, time_ms


class LucasSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode)-> str:
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
            print(f"Missing part file for {input_file}, missing suffix {part_suffix}")
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

        # TODO: need to save the output of the tool
        return result, time_ms

class Statistics():
    def __init__(self):
        self.stats = {'passed': 0, 'failed': 0, 'timeout': 0, 'other': 0, 'error': 0, 'inconsistent': 0}
        self.results = {} # test_path -> (time, status)
        self.lock = threading.Lock()


    def add_result(self, test_path, time, status, outcome):
        with self.lock:
            self.results[test_path] = (time, status)
            if outcome == 'passed': self.stats['passed'] += 1
            elif outcome == 'failed': self.stats['failed'] += 1
            elif outcome == 'timeout': self.stats['timeout'] += 1
            elif outcome == 'other': self.stats['other'] += 1
            elif outcome == 'error': self.stats['error'] += 1
            elif outcome == 'inconsistent': self.stats['inconsistent'] += 1

# for statistics 
statistics = Statistics()


def collectTest(testDir):
    global statistics
    p = Path(testDir).resolve()
    
    tests = []

    if p.is_file():
        if p.suffix == ".ltlf":
            test_files = [p]
        else:
            print(f"File {p} is not an .ltlf file.")
            return []
    else:
        test_files = list(p.rglob("**/ltlf/**/*.ltlf"))

    for file in test_files:
        test_path = file.resolve()
        
        # Try to find part file by replacing "ltlf" with "part" in the path
        parts = list(test_path.parts)
        if "ltlf" in parts:
            idx = parts.index("ltlf")
            part_parts = list(parts)
            part_parts[idx] = "part"
            part_file = Path(*part_parts).with_suffix(".part")
            
            if not part_file.exists():
                statistics.add_result(test_path, 0, 0, "other")
                print(f"Missing part file for {test_path} (expected at {part_file})")
                continue
            
            tests.append(test_path)
        else:
            print(f"Test file {test_path} not under an 'ltlf' directory, skipping.")

    return tests


TIMEOUT_CODE = -2
ERROR_CODE = -1

def executeTest(test, timeout, solver: Solver, mode="direct", iter=1):
    temp_dir = tempfile.mkdtemp()
    try:
        test_path = Path(test).resolve()
        test_name = test_path.name
        test_stem = test_path.stem
        
        # Strategy: find the index of "ltlf" in the parts of the path
        # and replace it with "part" or "mso" to find related files
        parts = list(test_path.parts)
        if "ltlf" not in parts:
            print(f"Error: {test} is not under an 'ltlf' directory.")
            return

        ltlf_idx = parts.index("ltlf")
        
        # Construct part file path
        part_parts = list(parts)
        part_parts[ltlf_idx] = "part"
        original_part = Path(*part_parts).with_suffix(".part")

        # Construct mso directory path
        mso_parts = list(parts)
        mso_parts[ltlf_idx] = "mso"
        mso_dir = Path(*mso_parts).parent

        inputfile = os.path.join(temp_dir, test_name)
        partfile = os.path.join(temp_dir, test_stem + ".part")

        # Copy the test files
        shutil.copy2(test, inputfile)
        if original_part.exists():
            shutil.copy2(original_part, partfile)
        else:
            print(f"Warning: Part file {original_part} not found.")
        
        # Copy DFA files if they exist (next to the .ltlf file)
        for dfa_suffix in [".dfa", ".dfa.rev.neg", ".dfa.quant"]:
            dfa_src = str(test) + dfa_suffix
            if os.path.exists(dfa_src):
                shutil.copy2(dfa_src, inputfile + dfa_suffix)
        
        # Copy part file variants if they exist
        for part_suffix in [".rev.neg", ".quant"]:
            part_src = str(original_part) + part_suffix
            if os.path.exists(part_src):
                shutil.copy2(part_src, partfile + part_suffix)
        
        # Copy .mona files from mso directory if they exist
        if mso_dir.exists():
            for mona_suffix in [".mona", ".mona.rev.neg", ".mona.quant"]:
                mona_src = mso_dir / (test_stem + mona_suffix)
                if mona_src.exists():
                    mona_dst = os.path.join(temp_dir, test_stem + mona_suffix)
                    shutil.copy2(mona_src, mona_dst)

        command = solver.get_command(inputfile, partfile, mode)
        if not command:
            return

        times = []
        results = []

        for i in range(iter):
            try:
                l = subprocess.check_output(command, timeout=timeout, shell=True, cwd=solver.path.parent)
                result, time = solver.parse_output(l)
                if result is None:
                    statistics.add_result(test, time, 0, "other")
                    print(f"Failed to parse output for {test}")
                    continue

                if result == 1:
                    results.append(1)
                else:
                    results.append(0)
                times.append(time)

            except subprocess.TimeoutExpired:
                print(f"Timeout for {test}")
                results.append(TIMEOUT_CODE)
                times.append(timeout)
                continue

            except subprocess.CalledProcessError as e:
                print(f"Failed to run {test}: {e}")
                results.append(ERROR_CODE)
                times.append(0)
                continue
        
        average_time = sum(times) / len(times) if times else 0

        if TIMEOUT_CODE in results:
            statistics.add_result(test, average_time, TIMEOUT_CODE, "timeout")
        elif ERROR_CODE in results:
            statistics.add_result(test, average_time, ERROR_CODE, "error")
        elif not all(elem == results[0] for elem in (results if results else [None])):
            statistics.add_result(test, average_time, -1, "inconsistent")
        else:
            status = results[0] if results else -1
            statistics.add_result(test, average_time, status, 'other')
    finally:
        shutil.rmtree(temp_dir)
        


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tests for Syft.")
    parser.add_argument("--timeout", type=int, default=1500, help="Timeout in seconds")
    parser.add_argument("--iter", type=int, default=1, help="Number of iterations")
    parser.add_argument("--mode", type=str, default="direct", help="Mode", choices=["direct", "belief", "mso"])
    parser.add_argument("--solver", type=str, default="lucas", help="Solver", choices=["lucas", "christian"])
    parser.add_argument("--path", type=str, default="~/lucas/Syft/build/bin/Syft", help="Path to Syft executable")
    parser.add_argument("--test-dir", type=str, default="lucas", help="Test directory")
    parser.add_argument("--output", type=str, default="results.csv", help="Output file")
    parser.add_argument("--shard-id", type=int, default=0, help="Shard index (0-indexed)")
    parser.add_argument("--num-shards", type=int, default=1, help="Total number of shards")
    args = parser.parse_args()

    # Expand user path and validate
    syft_path = Path(args.path).expanduser().resolve()
    if not syft_path.exists():
        print(f"Error: Syft executable not found at {syft_path}")
        print(f"Please specify the correct path using --path argument")
        sys.exit(1)

    test_dir = args.test_dir
    timeout = args.timeout
    iterations = args.iter
    mode = args.mode
    solver = ChristianSyftSolver(str(syft_path), name="christian") \
        if args.solver != 'lucas' else LucasSyftSolver(str(syft_path), name="lucas")
    tests = sorted(collectTest(test_dir))
    
    if args.num_shards > 1:
        total_tests = len(tests)
        tests = tests[args.shard_id::args.num_shards]
        print(f"Shard {args.shard_id}/{args.num_shards}: Running {len(tests)} out of {total_tests} tests.")
    else:
        print(f"Running all {len(tests)} tests.")

    for test in tests:
        executeTest(test, timeout, solver, mode, iterations)

    print("===========")
    print("Statistics:")
    print("===========")
    print(f"Passed: {statistics.stats['passed']}")
    print(f"Failed: {statistics.stats['failed']}")
    print(f"Timeout: {statistics.stats['timeout']}")
    print(f"Other: {statistics.stats['other']}")
    print(f"Error: {statistics.stats['error']}")
    print(f"Inconsistent: {statistics.stats['inconsistent']}")

    if not args.output:
        output_file = f"results_{args.solver}_{args.mode}.csv"
    else:
        output_file = args.output

    with open(output_file, "w") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["test", "time", "status"])
        for test, (time, status) in statistics.results.items():
            writer.writerow([test, time, status])



    