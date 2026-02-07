import os
import re
import unittest
import shutil
import tempfile
import subprocess
from pathlib import Path

# Add project root to path so we can import runTests
import sys
project_root = str(Path(__file__).parent.parent.resolve())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import runTests

# Constants
REPO_ROOT = Path(project_root)
LUCAS_SYFT_PATH = REPO_ROOT.parent / "lucas" / "Syft" / "build" / "bin" / "Syft"

class BaseSolverTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def get_expected(self, name):
        expected_file = REPO_ROOT / "lucas" / "expected" / f"{name}.txt"
        with open(expected_file, "r") as f:
            content = f.read().strip().lower()
            if content == "realizable":
                return 1
            elif content == "unrealizable":
                return 0
            return None

    def run_solver_logic(self, solver, example_name, ltlf_rel_path, mode, semantics="moore", on_the_fly=True):
        """
        Isolated test logic for a solver.
        Mimics execution steps in runTests.executeTest but runs in isolation.
        """
        expected_val = self.get_expected(example_name)
        self.assertIsNotNone(expected_val)
        
        ltlf_src = REPO_ROOT / ltlf_rel_path
        test_stem = ltlf_src.stem
        
        # Prepare artifacts using shared logic from runTests
        inputfile, partfile, semantics, _ = runTests.prepare_test_artifacts(
            ltlf_src, "part", solver, mode, 1, self.test_dir, semantics=semantics
        )

        # 1. Preprocess
        auto_time = solver.preprocess(inputfile, partfile, mode, semantics=semantics)
        
        # 2. Get command
        cmd = solver.get_command(inputfile, partfile, mode, semantics=semantics, on_the_fly=on_the_fly)
        self.assertTrue(cmd, f"Failed to get command for {example_name} in {mode}")
        
        # 3. Execute
        try:
            # We use shell=True because some solvers return complex command strings (pipes, redirects)
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=60, cwd=REPO_ROOT)
        except subprocess.CalledProcessError as e:
            output = e.output
        
        # 4. Parse output
        result, t_ms, t_src = solver.parse_output(output)
        
        self.assertEqual(result, expected_val, f"Solver {solver.get_name()} for {example_name} ({mode}) returned {result}, expected {expected_val}. Output: {output.decode()}")

class TestLucasSolvers(BaseSolverTest):
    def test_lucas_benchmarks(self):
        benchmarks = [
            ("peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf"),
            ("peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf"),
            ("peek_3_3_54", "lucas/ltlf/peek/peek_3_3_54.ltlf"),
            ("peek_4_4_87", "lucas/ltlf/peek/peek_4_4_87.ltlf"),
            ("coins_3", "lucas/ltlf/coins_3.ltlf"),
            ("coins_4", "lucas/ltlf/coins_4.ltlf"),
            ("seek_5", "lucas/ltlf/seek_5.ltlf"),
        ]
        
        modes = ["belief-states", "mso", "projection"]
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        
        for name, path in benchmarks:
            for mode in modes:
                with self.subTest(benchmark=name, mode=mode):
                    self.run_solver_logic(solver, name, path, mode)

class TestSpotSolvers(BaseSolverTest):
    def test_spot_benchmarks(self):
        benchmarks = [
            ("peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf"),
            ("peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf"),
            ("peek_3_3_54", "lucas/ltlf/peek/peek_3_3_54.ltlf"),
            ("peek_4_4_87", "lucas/ltlf/peek/peek_4_4_87.ltlf"),
            ("peek_4_3_68", "lucas/ltlf/peek/peek_4_3_68.ltlf"),
            ("coins_3", "lucas/ltlf/coins_3.ltlf"),
            ("coins_4", "lucas/ltlf/coins_4.ltlf"),
            ("seek_5", "lucas/ltlf/seek_5.ltlf"),
        ]
        
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        
        for name, path in benchmarks:
            for on_the_fly in [True, False]:
                mode_name = "ltlf_otf" if on_the_fly else "ltlf_restricted"
                with self.subTest(benchmark=name, mode=mode_name):
                    self.run_solver_logic(solver, name, path, "ltlf", on_the_fly=on_the_fly)

class TestGames(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_game_test(self, solver, ltlf_path, level, expected_val, mode, sample_id=1):
        ltlf_src = REPO_ROOT / ltlf_path
        test_stem = ltlf_src.stem
        
        if level == "part":
            part_dir_name = "part"
        elif level == "all":
            part_dir_name = "po-part-all"
        else:
            part_dir_name = f"po-part-{level}"

        actual_temp = tempfile.mkdtemp(dir=self.test_dir)
        try:
            benchmark_root = REPO_ROOT / "ltlf-fin-benchmarks"
            inputfile, partfile, actual_semantics, _ = runTests.prepare_test_artifacts(
                ltlf_src, part_dir_name, solver, mode, sample_id, actual_temp, test_dir_origin=benchmark_root
            )

            # Preprocess and execute
            auto_time = solver.preprocess(inputfile, partfile, mode, semantics=actual_semantics)
            cmd = solver.get_command(inputfile, partfile, mode, semantics=actual_semantics)
            self.assertTrue(cmd)
            
            try:
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=60, cwd=REPO_ROOT)
            except subprocess.CalledProcessError as e:
                output = e.output
            
            result, _, _ = solver.parse_output(output)
            self.assertEqual(result, expected_val, f"Solver {solver.get_name()} for {ltlf_path} ({mode}) at level {level} (sample {sample_id}) returned {result}, expected {expected_val}. Output: {output.decode()}")
        finally:
            shutil.rmtree(actual_temp)

    def test_counter(self):
        solvers = [(runTests.SpotSolver("ltlfsynt", name="spot"), "ltlf"), (runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas"), "belief-states"), (runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas"), "mso")]
        for solver, mode in solvers:
            for level, sample_id, expected in [("part", 1, 1), ("all", 1, 0), ("1-2", 1, 0)]:
                with self.subTest(level=level, sample_id=sample_id, solver=solver.get_name(), mode=mode):
                    self.run_game_test(solver, "ltlf-fin-benchmarks/ltlf/counter_pb_01_pe_.ltlf", level, expected, mode, sample_id=sample_id)

    def test_nim_real(self):
        solvers = [(runTests.SpotSolver("ltlfsynt", name="spot"), "ltlf"), (runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas"), "belief-states"), (runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas"), "mso")]
        for solver, mode in solvers:
            for level, sample_id, expected in [("part", 1, 0), ("all", 1, 0)]:
                with self.subTest(level=level, sample_id=sample_id, solver=solver.get_name(), mode=mode):
                    self.run_game_test(solver, "ltlf-fin-benchmarks/ltlf/nim_pb_02_03_pe_.ltlf", level, expected, mode, sample_id=sample_id)

if __name__ == "__main__":
    unittest.main()
