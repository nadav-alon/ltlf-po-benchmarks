import subprocess
import os
import re
import csv 
from pathlib import Path
import time 
import tempfile
import argparse
import threading


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


def get_safe_true(part_file):
    vars = get_variables_from_part(part_file)
    if not vars:
        return "true"
    # Return a list of tautologies, one for each variable
    return " && ".join([f"{v} | ~{v}" for v in vars])

class ChristianSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode)-> str:
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
                    content = f.read()
                with open(christian_input, 'w') as f:
                    f.write(content+'\n'+get_safe_true(part_file))
            input_file = christian_input
        

        christian_dfa = input_file + '.christian.dfa'
        if not os.path.exists(christian_dfa):
            # Run MONA on the source file to get the DFA
            mona_out = subprocess.run(["mona", "-u", "-xw", input_file], text=True, capture_output=True)
            with open(christian_dfa, 'w') as f:
                f.write(mona_out.stdout)
        
        return f'"{self.path}" {christian_dfa} {part_file} 0 {mode}'

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
    p = Path(testDir)
    part_dir = p / "part" 

    tests = []

    for file in p.rglob("*/*.ltlf"):
        tests.append(file)
        test_name = file.name.replace(".ltlf", "")

        if not (part_dir / (test_name + ".part")).exists():
            statistics.add_result(file, 0, 0, "other")
            print(f"Missing part file for {file}")
            continue

    return tests


TIMEOUT_CODE = -2
ERROR_CODE = -1

def executeTest(test, timeout, solver: Solver, mode="direct", iter=1):
    temp_dir = tempfile.mkdtemp()

    inputfile = os.path.join(temp_dir, test)
    partfile = os.path.join(temp_dir, str(test) + '.part')

    command = solver.get_command(inputfile, partfile, mode)
    times = []
    results = []

    for i in range(iter):
        try:
            l = subprocess.check_output(command, timeout=timeout, shell=True, cwd=solver.path)
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
    elif not all(elem == results[0] for elem in results):
        statistics.add_result(test, average_time, -1, "inconsistent")
    else:
        statistics.add_result(test, average_time, -1 if len(results) == 0 else results[0], 'other')
        


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tests for Syft.")
    parser.add_argument("--timeout", type=int, default=1500, help="Timeout in seconds")
    parser.add_argument("--iter", type=int, default=1, help="Number of iterations")
    parser.add_argument("--mode", type=str, default="direct", help="Mode", choices=["direct", "iterative"])
    parser.add_argument("--solver", type=str, default="lucas", help="Solver", choices=["lucas", "christian"])
    parser.add_argument("--path", type=str, default="", help="Path to Syft executable")
    parser.add_argument("--test-dir", type=str, default="lucas", help="Test directory")
    parser.add_argument("--output", type=str, default="results.csv", help="Output file")
    args = parser.parse_args()

    test_dir = args.test_dir
    timeout = args.timeout
    iterations = args.iter
    mode = args.mode
    solver = ChristianSyftSolver(args.path, name="christian") \
        if args.solver != 'lucas' else LucasSyftSolver(args.path, name="lucas")
    tests = collectTest(test_dir)
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



    