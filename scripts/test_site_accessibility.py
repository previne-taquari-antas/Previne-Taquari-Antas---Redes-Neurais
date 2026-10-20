"""Protect build-time enhancements on generated and nested reports."""
import tempfile
import unittest
from pathlib import Path
from apply_institutional_logos import brand_page, PageStructure

class AccessibilityBuildTest(unittest.TestCase):
    def test_nested_report_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); page=root/'reports/nested/index.html';page.parent.mkdir(parents=True)
            page.write_text('<html lang="pt-BR"><head><title>Report</title></head><body><main><table><tr><td>123</td></tr></table></main></body></html>')
            self.assertEqual(brand_page(page,root),'added')
            built=page.read_text()
            self.assertIn('../../assets/js/site_accessibility.js',built)
            self.assertIn('name="viewport"',built)
            self.assertIn('<td>123</td>',built)
            self.assertEqual(brand_page(page,root),'already_present')
            self.assertEqual(page.read_text(),built)
    def test_existing_viewport_and_redirect(self):
        self.assertTrue(PageStructure("<html><head><meta name='viewport' content='width=device-width'/></head><body></body></html>").has_viewport)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);page=root/'index.html'
            source='<html><head><meta http-equiv="refresh" content="0;url=other.html"></head><body></body></html>'
            page.write_text(source)
            self.assertEqual(brand_page(page,root),'redirect')
            self.assertEqual(page.read_text(),source)

if __name__=='__main__':unittest.main()
