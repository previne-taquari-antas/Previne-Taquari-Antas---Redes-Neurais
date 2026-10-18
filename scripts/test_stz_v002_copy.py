"""Run the real V002 copy callbacks; exported drafts must retain their limits.

Only clipboard/DOM are recorders. No alert, publication, model or field claim.
STZ_V002_TEST_REF optionally reads a historical source for counterproof.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAGE = "pesquisas/estudo-caso-resposta-santa-tereza.html"
WARNING = "RASCUNHO DO EXERCÍCIO — NÃO É ALERTA, ORDEM DE EVACUAÇÃO OU DESPACHO"


class V002CopyTests(unittest.TestCase):
    def copied(self, mode):
        reference = os.environ.get("STZ_V002_TEST_REF")
        if reference:
            source = subprocess.run(["git", "show", reference + ":" + PAGE], cwd=ROOT,
                                    capture_output=True, text=True, encoding="utf-8", check=True).stdout
        else:
            source = (ROOT / PAGE).read_text(encoding="utf-8")
        functions = []
        for name in ("copyMessage", "copyMessageFallback"):
            match = re.search(r"^    function " + name + r"\([^\n]*\{[\s\S]*?^    \}", source, re.M)
            self.assertIsNotNone(match, "actual callback missing: " + name)
            functions.append(match.group(0))
        code = r"""
const vm=require('node:vm'),clipboard=[],fallback=[],announcements=[];
let area=null,removed=0;
const ctx={
 el:()=>({textContent:'RASCUNHO — NÃO É ALERTA · Z-01: hipótese do exercício, sem deslocamento real.'}),
 announce:text=>announcements.push(text),navigator:{},
 document:{createElement:()=>({value:'',style:{},setAttribute(){},select(){},remove(){removed++;}}),
  body:{appendChild:element=>{area=element;}},execCommand:command=>{if(command!=='copy')throw Error(command);fallback.push(area.value);return true;}}};
if(MODE!=='missing')ctx.navigator.clipboard={writeText:text=>{clipboard.push(text);
 return MODE==='reject'?Promise.reject(Error('permission denied')):Promise.resolve();}};
vm.createContext(ctx);vm.runInContext(FUNCTIONS,ctx);ctx.copyMessage();
setImmediate(()=>console.log(JSON.stringify({clipboard,fallback,announcements,removed})));
""".replace("FUNCTIONS", json.dumps("\n".join(functions))).replace("MODE", json.dumps(mode))
        result = subprocess.run([shutil.which("node") or "node", "-e", code], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        for text in output["clipboard"] + output["fallback"]:
            self.assertTrue(text.startswith(WARNING + "\n\n"), text)
            self.assertEqual(text.count(WARNING), 1)
            self.assertIn("Z-01: hipótese do exercício, sem deslocamento real.", text)
            self.assertNotIn("NÃO É ALERTA ·", text, "visual prefix must not be duplicated in copied body")
        self.assertTrue(output["announcements"])
        return output

    def test_clipboard_success_retains_non_operational_warning(self):
        result = self.copied("success")
        self.assertEqual(len(result["clipboard"]), 1)
        self.assertEqual(result["fallback"], [])

    def test_missing_clipboard_fallback_retains_warning(self):
        result = self.copied("missing")
        self.assertEqual(result["clipboard"], [])
        self.assertEqual(len(result["fallback"]), 1)
        self.assertEqual(result["removed"], 1)

    def test_rejected_clipboard_uses_identical_safe_fallback(self):
        result = self.copied("reject")
        self.assertEqual(len(result["clipboard"]), 1)
        self.assertEqual(result["fallback"], result["clipboard"])
        self.assertEqual(result["removed"], 1)


if __name__ == "__main__":
    unittest.main()
