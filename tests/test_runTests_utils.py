import unittest
import os
import tempfile
import json
import shutil
from pathlib import Path
from runTests import (
    normalize_part_with_dots,
    quantify_mona_content,
    negate_mona_content,
    load_samples,
    filter_part_file_for_lucas,
    Statistics,
    SAMPLES_CACHE
)

class TestRunTestsFunctions(unittest.TestCase):

    # --- normalize_part_with_dots ---
    def test_normalize_part_with_dots_basic(self):
        content = "inputs: a b\noutputs: c\nsemantics: moore\nunobservables: d"
        expected = ".inputs: a b\n.outputs: c\n.unobservables: d"
        self.assertEqual(normalize_part_with_dots(content).strip(), expected.strip())

    def test_normalize_part_with_dots_already_dotted(self):
        content = ".inputs: a b\n.outputs: c"
        self.assertEqual(normalize_part_with_dots(content).strip(), content.strip())

    def test_normalize_part_with_dots_ignores_semantics(self):
        content = "inputs: i\nsemantics: mealy\noutputs: o"
        expected = ".inputs: i\n.outputs: o"
        self.assertEqual(normalize_part_with_dots(content).strip(), expected.strip())

    # --- quantify_mona_content ---
    def test_quantify_mona_content_basic(self):
        # Mocks a simple MONA file content
        mona_content = """# Header
m2l-str;
var2 A, B, C;
# Body
formula;
"""
        unobservables = ["B"]
        result = quantify_mona_content(mona_content, unobservables)
        
        self.assertIn("all2 B: (", result)
        self.assertIn("var2 A, C;", result)
        self.assertNotIn("var2 A, B, C;", result)  # B should be removed from free vars
        self.assertTrue(result.strip().endswith(");"))

    def test_quantify_mona_content_no_unobs(self):
        mona_content = "var2 A;\nformula;"
        unobservables = []
        result = quantify_mona_content(mona_content, unobservables)
        self.assertIn("var2 A;", result)
        self.assertNotIn("all2", result)
        self.assertEqual(result.strip(), "var2 A;\nformula;")

    # --- negate_mona_content ---
    def test_negate_mona_content(self):
        mona_content = """m2l-str;
var2 A;
# comment
(p & q);
"""
        result = negate_mona_content(mona_content)
        self.assertIn("var2 A;", result)
        self.assertIn("~((p & q));", result)
        self.assertTrue(result.strip().endswith(";"))

    # --- filter_part_file_for_lucas ---
    def test_filter_part_file_for_lucas(self):
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
            f.write("inputs: i1 i2 u1\noutputs: o1\nunobservables: u1")
            path = f.name
        
        try:
            filter_part_file_for_lucas(path)
            with open(path, 'r') as f:
                new_content = f.read()
            
            self.assertIn("inputs: i1 i2", new_content)
            self.assertNotIn("inputs: i1 i2 u1", new_content)
            self.assertIn("unobservables: u1", new_content)
        finally:
            os.remove(path)

    def test_filter_part_file_for_lucas_dotted(self):
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
            f.write(".inputs: i1 u1\n.unobservables: u1")
            path = f.name
        
        try:
            filter_part_file_for_lucas(path)
            with open(path, 'r') as f:
                new_content = f.read()
            
            self.assertIn(".inputs: i1", new_content)
            self.assertNotIn(".inputs: i1 u1", new_content)
        finally:
            os.remove(path)

    # --- load_samples ---
    def test_load_samples(self):
        # Setup directory structure
        tmpdir = tempfile.mkdtemp()
        try:
            samples_data = {"key": ["val"]}
            with open(os.path.join(tmpdir, "samples.json"), "w") as f:
                json.dump(samples_data, f)
            
            subdir = os.path.join(tmpdir, "subdir")
            os.mkdir(subdir)
            
            # Clear cache to force reload
            SAMPLES_CACHE.clear()
            
            # Load from subdir
            result = load_samples(subdir)
            self.assertEqual(result, samples_data)
            
            # Check cache
            samples_path = str(Path(os.path.join(tmpdir, "samples.json")).resolve())
            self.assertIn(samples_path, SAMPLES_CACHE)
            
            # Helper to ensure cache works
            SAMPLES_CACHE[samples_path] = {"cached": True}
            result_cached = load_samples(subdir)
            self.assertEqual(result_cached, {"cached": True})
            
        finally:
            shutil.rmtree(tmpdir)
            SAMPLES_CACHE.clear()

    # --- Statistics ---
    def test_statistics(self):
        stats = Statistics()
        
        # Add a realizable result
        stats.add_result("test1", 100, 10, 5, 1, "realizable", verified=True, time_source="tool")
        
        self.assertEqual(stats.stats['realizable'], 1)
        self.assertEqual(stats.stats['verified'], 1)
        self.assertIn("test1", stats.results)
        self.assertEqual(stats.results["test1"][0], 100) # time
        
        # Add a timeout
        stats.add_result("test2", 2000, 0, 0, -2, "timeout")
        self.assertEqual(stats.stats['timeout'], 1)
        
        # Add a failed verification
        stats.add_result("test3", 150, 10, 5, 1, "realizable", verified=False)
        self.assertEqual(stats.stats['verification_failed'], 1)
        self.assertEqual(stats.stats['realizable'], 2) # Incremented again

if __name__ == "__main__":
    unittest.main()
