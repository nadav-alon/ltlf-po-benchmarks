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
        print(f"\nDEBUG: Preprocessed {example_name} in {mode} ({partfile})")
        with open(partfile, 'r') as f:
            print(f"DEBUG: Part File ({partfile}):\n{f.read()}")
        
        with open(inputfile, 'r') as f:
            print(f"DEBUG: Input File ({inputfile}):\n{f.read()}")
        
        # 2. Get command
        cmd = solver.get_command(inputfile, partfile, mode, semantics=semantics, on_the_fly=on_the_fly)
        print(f"DEBUG: Command for {example_name} in {mode}:\n{cmd}")
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

class TestLucasBeliefStates(BaseSolverTest):
    def test_lucas_bs_peek_1_1_1(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "belief-states")

    def test_lucas_bs_peek_1_1_89(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "belief-states")
    
    def test_lucas_bs_coins_3(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "belief-states")

    def test_lucas_bs_coins_4(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "belief-states")

    def test_lucas_bs_seek_5(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "belief-states")

class TestLucasMSO(BaseSolverTest):
    def test_lucas_mso_peek_1_1_1(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "mso")

    def test_lucas_mso_peek_1_1_89(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "mso")

    def test_lucas_mso_coins_3(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "mso")

    def test_lucas_mso_coins_4(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "mso")

    def test_lucas_mso_seek_5(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "mso")

class TestSpotLTLf(BaseSolverTest):
    def test_spot_ltlf_coins_3(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "ltlf")

    def test_spot_ltlf_coins_4(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "ltlf")

    def test_spot_ltlf_seek_5(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "ltlf")

    def test_spot_ltlf_peek_1_1_1(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "ltlf")

    def test_spot_ltlf_peek_1_1_89(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "ltlf")

    def test_spot_ltlf_peek_4_3_68(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_4_3_68", "lucas/ltlf/peek/peek_4_3_68.ltlf", "ltlf")

class TestSpotLTLf_restricted(BaseSolverTest):
    def test_spot_ltlf_coins_3(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "ltlf", on_the_fly=False)

    def test_spot_ltlf_coins_4(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "ltlf", on_the_fly=False)

    def test_spot_ltlf_seek_5(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "ltlf", on_the_fly=False)

    def test_spot_ltlf_peek_1_1_1(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "ltlf", on_the_fly=False)

    def test_spot_ltlf_peek_1_1_89(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "ltlf", on_the_fly=False)

    def test_spot_ltlf_peek_4_3_68(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_4_3_68", "lucas/ltlf/peek/peek_4_3_68.ltlf", "ltlf", on_the_fly=False)

class TestLucasProjection(BaseSolverTest):
    def test_lucas_proj_peek_1_1_1(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "projection")

    def test_lucas_proj_peek_1_1_89(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "projection")
    
    def test_lucas_proj_coins_3(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "projection")

    def test_lucas_proj_coins_4(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "projection")

    def test_lucas_proj_seek_5(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        # Fixed copy-paste error: explicitly using "projection" mode as per method name intention
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "projection")


class TestGames(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_game_test(self, solver, ltlf_path, level, expected_val, mode, sample_id=1):
        ltlf_src = REPO_ROOT / ltlf_path
        test_stem = ltlf_src.stem
        
        # Determine part directory name (matching runTests logic)
        if level == "part":
            part_dir_name = "part"
        elif level == "all":
            part_dir_name = "po-part-all"
        else:
            part_dir_name = f"po-part-{level}"

        # We should use a unique name for the partfile in the shared test_dir if multiple subtests run
        # However, prepare_test_artifacts uses test_stem + ".part" inside temp_dir.
        # Since we use a fresh temp_dir in execTest but here self.test_dir is reused?
        # No, run_game_test is called within a test method, and setUp/tearDown handle self.test_dir.
        # But wait, test_spot_counter runs multiple subTests!
        # I should probably use a unique temp_dir per run_game_test call too, or make prepare_test_artifacts more flexible.
        
        actual_temp = tempfile.mkdtemp(dir=self.test_dir)
        try:
            # Use same logic as runTests.py
            benchmark_root = REPO_ROOT / "ltlf-fin-benchmarks"
            inputfile, partfile, actual_semantics, _ = runTests.prepare_test_artifacts(
                ltlf_src, part_dir_name, solver, mode, sample_id, actual_temp, test_dir_origin=benchmark_root
            )

            print(f"DEBUG: inputfile {inputfile}")
            with open(inputfile, 'r') as f:
                print(f"DEBUG: inputfile content {f.read()}")
            print(f"DEBUG: partfile {partfile}")
            if os.path.exists(partfile):
                with open(partfile, 'r') as f:
                    print(f"DEBUG: partfile content {f.read()}")
            print(f"DEBUG: actual_semantics {actual_semantics}")

            # Preprocess and execute
            auto_time = solver.preprocess(inputfile, partfile, mode, semantics=actual_semantics)
            print(f"DEBUG: auto time {auto_time} for {test_stem} at {level}")
            cmd = solver.get_command(inputfile, partfile, mode, semantics=actual_semantics)
            print(f"DEBUG: cmd {cmd}")
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
        # All modes are realizable for this small counter instance
        for solver, mode in solvers:
            for level, sample_id, expected in [("part", 1, 1), ("all", 1, 0), ("1-2", 1, 0)]:
                with self.subTest(level=level, sample_id=sample_id, solver=solver.get_name(), mode=mode):
                    self.run_game_test(solver, "ltlf-fin-benchmarks/ltlf/counter_pb_01_pe_.ltlf", level, expected, mode, sample_id=sample_id)

    def test_nim_real(self):
        solvers = [(runTests.SpotSolver("ltlfsynt", name="spot"), "ltlf"), (runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas"), "belief-states"), (runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas"), "mso")]
        # Nim is realizable for system here
        for solver, mode in solvers:
            for level, sample_id, expected in [("part", 1, 0), ("all", 1, 0)]:
                with self.subTest(level=level, sample_id=sample_id, solver=solver.get_name(), mode=mode):
                    self.run_game_test(solver, "ltlf-fin-benchmarks/ltlf/nim_pb_02_03_pe_.ltlf", level, expected, mode, sample_id=sample_id)

if __name__ == "__main__":
    unittest.main()
