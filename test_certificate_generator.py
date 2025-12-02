"""
Unit tests for Certificate Generator
"""

import unittest
import json
import tempfile
from pathlib import Path
from certificate_generator import CertificateGenerator


class TestCertificateGenerator(unittest.TestCase):
    """Test suite for CertificateGenerator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.generator = CertificateGenerator()
        self.temp_dir = tempfile.TemporaryDirectory()
    
    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()
    
    def test_default_template(self):
        """Test default template configuration."""
        template = CertificateGenerator._default_template()
        self.assertIn("title", template)
        self.assertIn("subtitle", template)
        self.assertIn("issuer", template)
    
    def test_generate_certificate(self):
        """Test single certificate generation."""
        filepath = self.generator.generate_certificate(
            recipient_name="Test User",
            course_name="Test Course"
        )
        self.assertTrue(filepath.exists())
        self.assertTrue(str(filepath).endswith(".pdf"))
    
    def test_certificate_naming(self):
        """Test certificate file naming."""
        filepath = self.generator.generate_certificate(
            recipient_name="John Doe",
            course_name="Python Basics"
        )
        self.assertIn("John_Doe", str(filepath))
    
    def test_custom_output_filename(self):
        """Test custom output filename."""
        custom_name = "my_certificate.pdf"
        filepath = self.generator.generate_certificate(
            recipient_name="Test User",
            course_name="Test Course",
            output_filename=custom_name
        )
        self.assertTrue(str(filepath).endswith(custom_name))
    
    def test_batch_generation(self):
        """Test batch certificate generation."""
        recipients = [
            {"name": "Alice", "course": "Course 1"},
            {"name": "Bob", "course": "Course 2"},
            {"name": "Charlie", "course": "Course 3"},
        ]
        paths = self.generator.generate_batch(recipients)
        self.assertEqual(len(paths), 3)
        for path in paths:
            self.assertTrue(path.exists())
    
    def test_rgb_to_hex_conversion(self):
        """Test RGB to hex color conversion."""
        hex_color = CertificateGenerator._rgb_to_hex((255, 0, 0))
        self.assertEqual(hex_color, "#ff0000")
        
        hex_color = CertificateGenerator._rgb_to_hex((70, 130, 180))
        self.assertEqual(hex_color, "#4682b4")
    
    def test_load_recipients_from_json(self):
        """Test loading recipients from JSON file."""
        recipients_data = [
            {"name": "Test User", "course": "Test Course"}
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(recipients_data, f)
            temp_file = f.name
        
        try:
            loaded = self.generator.load_recipients_from_json(temp_file)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["name"], "Test User")
        finally:
            Path(temp_file).unlink()
    
    def test_load_template_from_json(self):
        """Test loading template configuration from JSON file."""
        template_data = {
            "title": "Custom Certificate",
            "issuer": "Custom Issuer"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(template_data, f)
            temp_file = f.name
        
        try:
            self.generator.load_template_from_json(temp_file)
            self.assertEqual(self.generator.template_config["title"], "Custom Certificate")
            self.assertEqual(self.generator.template_config["issuer"], "Custom Issuer")
        finally:
            Path(temp_file).unlink()


if __name__ == '__main__':
    unittest.main()
