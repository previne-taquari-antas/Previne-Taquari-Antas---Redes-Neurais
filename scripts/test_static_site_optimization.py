import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('optimizer',Path(__file__).with_name('optimize_static_site.py'))
optimizer=importlib.util.module_from_spec(spec);spec.loader.exec_module(optimizer)

class StaticOptimizationTests(unittest.TestCase):
    def test_preserves_json_and_executable_bytes_and_shares_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'pesquisas').mkdir();(root/'assets/js').mkdir(parents=True)
            (root/'assets/js/shared.js').write_text('window.shared=true;')
            payload=json.dumps({'series':list(range(12000)),'text':'á água < & >'})
            executable='window.payloadLength=12000;\n'+'// preserved\n'*4000
            html='<script id="data" type="application/json">'+payload+'</script><script>'+executable+'</script><script src="assets/js/shared.js?v=old"></script>'
            (root/'index.html').write_text(html);(root/'other.html').write_text(html)
            stats=optimizer.optimize(root);self.assertEqual(stats['assets'],2)
            self.assertLess((root/'index.html').stat().st_size,1000)
            self.assertNotIn('?v=old',(root/'index.html').read_text())
            contents=[p.read_text() for p in (root/'assets/generated').glob('*.js')]
            self.assertIn(executable,contents)
            assignment=next(s for s in contents if 'textContent=' in s)
            restored=json.loads(assignment.split('.textContent=',1)[1].rstrip('\n;'))
            self.assertEqual(restored,payload)
            self.assertEqual(json.loads(restored)['series'],list(range(12000)))
            again=optimizer.optimize(root);self.assertEqual(again['assets'],0)

if __name__=='__main__':unittest.main()
