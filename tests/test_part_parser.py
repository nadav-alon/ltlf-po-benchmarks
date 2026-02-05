import unittest
import tempfile
import os
import shutil
from runTests import get_variables_from_part

class TestPartParser(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.part_file = os.path.join(self.test_dir, "test.part")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def create_part_file(self, content):
        with open(self.part_file, "w") as f:
            f.write(content)

    def test_standard_colon(self):
        content = """
inputs: i1 i2
outputs: o1 o2
        """
        self.create_part_file(content)
        
        inputs = get_variables_from_part(self.part_file, "inputs")
        self.assertEqual(inputs, ["i1", "i2"])
        
        outputs = get_variables_from_part(self.part_file, "outputs")
        self.assertEqual(outputs, ["o1", "o2"])

    def test_standard_space(self):
        content = """
inputs i1 i2
outputs o1 o2
        """
        self.create_part_file(content)
        
        inputs = get_variables_from_part(self.part_file, "inputs")
        self.assertEqual(inputs, ["i1", "i2"])
        
        outputs = get_variables_from_part(self.part_file, "outputs")
        self.assertEqual(outputs, ["o1", "o2"])

    def test_dot_colon(self):
        content = """
.inputs: i1 i2
.outputs: o1 o2
        """
        self.create_part_file(content)
        
        inputs = get_variables_from_part(self.part_file, "inputs")
        self.assertEqual(inputs, ["i1", "i2"])
        
        outputs = get_variables_from_part(self.part_file, "outputs")
        self.assertEqual(outputs, ["o1", "o2"])

    def test_dot_space(self):
        # This format is arguably ambiguous or unsupported by current logic, 
        # but let's test if it's expected to work or we need to fix the parser.
        content = """
.inputs i1 i2
.outputs o1 o2
        """
        self.create_part_file(content)
        
        inputs = get_variables_from_part(self.part_file, "inputs")
        # Current logic might fail here. We'll assertions to see behavior.
        # If it fails, I might need to fix the parser code.
        self.assertEqual(inputs, ["i1", "i2"])
        
        outputs = get_variables_from_part(self.part_file, "outputs")
        self.assertEqual(outputs, ["o1", "o2"])

    def test_mixed_formats(self):
        content = """
inputs: i1
.inputs: i2
inputs i3
.outputs: o1
outputs o2
        """
        self.create_part_file(content)
        
        inputs = get_variables_from_part(self.part_file, "inputs")
        self.assertEqual(sorted(inputs), ["i1", "i2", "i3"])
        
        outputs = get_variables_from_part(self.part_file, "outputs")
        self.assertEqual(sorted(outputs), ["o1", "o2"])

    def test_all_variables(self):
        content = """
inputs: i1
outputs: o1
unobservables: u1
        """
        self.create_part_file(content)
        
        all_vars = get_variables_from_part(self.part_file, "all")
        self.assertEqual(sorted(all_vars), ["i1", "o1", "u1"])

    def test_all_variables_dot(self):
        content = """
.inputs: i1
.outputs: o1
.unobservables: u1
        """
        self.create_part_file(content)
        
        all_vars = get_variables_from_part(self.part_file, "all")
        self.assertEqual(sorted(all_vars), ["i1", "o1", "u1"])

    def test_multiline_implicit(self):
        # Not sure if multiline is supported, usually part files are line-based.
        # But redundant lines should accumulate.
        content = """
inputs: i1
inputs: i2
        """
        self.create_part_file(content)
        inputs = get_variables_from_part(self.part_file, "inputs")
        self.assertEqual(sorted(inputs), ["i1", "i2"])

if __name__ == "__main__":
    unittest.main()
