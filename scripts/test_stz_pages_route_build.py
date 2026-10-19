"""Pages-only route build gate; no Git writes, inference or operational approval.

The real, previously tested generator runs on the immutable checkout's feed.
This gate reconciles its JSON and HTML before branding/upload, at the recorded
evaluation time. Arithmetic/NoData/temporal edge cases have separate tests.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
import copy
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def generator(root: Path):
    spec = importlib.util.spec_from_file_location(
        "stz_pages_route_generator", ROOT / "codigo_python/09_rota_fuga/gerar_rota_fuga_santa_tereza.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RAIZ = str(root)
    module.PAGINA_HAND = str(root / "santa_tereza_previsao_inundacao.html")
    module.FORECAST = str(root / "previsao_ao_vivo.json")
    return module


def validate_product(root: Path) -> dict:
    route = generator(root)
    product = json.loads((root / "assets/data/rota_fuga_santa_tereza.json").read_text(encoding="utf-8"))
    meta = product["meta"]
    expected = {
        "schema_version": "stz_route_research_v2",
        "cenario": "ao_vivo", "argumento_cenario": "ao_vivo",
        "zero_regua_m": 1.6, "status": "pesquisa_exercicio_nao_operacional",
        "formula_regua_para_hand": "HAND = max(0, regua_m - 1.60)",
        "ponto_seguro": route.PONTO_SEGURO,
    }
    if any(meta.get(key) != value for key, value in expected.items()):
        raise ValueError("produto de rota sem contrato atual de pesquisa/campo")
    hand, geo = route.carrega_hand()  # includes PNG digest, NoData and saturation validation
    if meta["raster_contract"] != geo["raster_contract"]:
        raise ValueError("produto e fonte raster divergentes")
    forecast = json.loads((root / "previsao_ao_vivo.json").read_text(encoding="utf-8"))
    evaluated = meta["temporal"]["avaliado_em"]
    checked = route._hora(evaluated)
    generated = route._hora(meta["gerado_em"])
    if not 0 <= (generated - checked).total_seconds() <= 60:
        raise ValueError("avaliação não corresponde à geração deste produto")
    # The generator uses tuples internally; JSON stores those as arrays.
    temporal = json.loads(json.dumps(route.trajetoria_nivel(forecast, now=evaluated, cenario="ao_vivo"), allow_nan=False))
    if meta["temporal"] != temporal or meta["aviso"] != temporal["caveat"]:
        raise ValueError("produto e feed/validade temporal divergentes")
    cells, dy, dx = route.monta_quadras(hand, geo, temporal)
    frequencies = Counter(cell["classe"] for cell in cells)
    counts = {name: frequencies[name] for name in route.CORES}
    if product["quadras"] != cells or product["resumo"] != counts:
        raise ValueError("quadras/resumo divergentes do terreno e trajetória publicados")
    level = temporal["nivel_atual_cm"]
    level_text = (f"{level/100:.2f} m (régua de referência)"
                  if level is not None and temporal["status"] != "telemetria_indisponivel"
                  else "telemetria indisponível para estimativa")
    if (meta["nivel_txt"] != level_text or meta["nivel_atual_cm"] != level
            or meta["cenario_rotulo"] != temporal["rotulo"]):
        raise ValueError("rótulos de nível/cenário divergentes")
    actual = (root / "santa_tereza_rota_fuga.html").read_text(encoding="utf-8")
    if actual != route.render_html(cells, dy, dx, meta, counts):
        raise ValueError("HTML/JSON de rota divergentes antes da transformação institucional")
    return {"status": temporal["status"], "avaliado_em": evaluated,
            "horizontes_aceitos": temporal["horizontes_aceitos"],
            "source_id": geo["raster_contract"]["source_id"], "quadras": len(cells)}


class PagesRouteBuildTests(unittest.TestCase):
    def fixture(self, forecast=None, now=None):
        import test_rota_fuga_santa_tereza_field as fixtures
        folder = tempfile.TemporaryDirectory(prefix="stz-pages-route-")
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        payload = fixtures.raster_fixture([[0, 255, 250, 30]])
        (root / "santa_tereza_previsao_inundacao.html").write_text(
            '<script id="hand-data" type="application/json">' + json.dumps(payload) + '</script>',
            encoding="utf-8")
        (root / "previsao_ao_vivo.json").write_text(
            json.dumps(forecast if forecast is not None else fixtures.forecast_fixture()), encoding="utf-8")
        route = generator(root)
        actual_datetime = dt.datetime
        clock = route._hora(now) if now is not None else actual_datetime.now(dt.timezone.utc)

        class FixedDatetime(actual_datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(clock.timestamp(), tz=tz)

        with (mock.patch.object(sys, "argv", ["route", "--cenario", "ao_vivo"]),
              mock.patch.object(route.dt, "datetime", FixedDatetime), redirect_stdout(io.StringIO())):
            route.main()
        return root

    def test_real_build_accepts_stale_feed_without_false_crossing(self):
        root = self.fixture()
        result = validate_product(root)
        self.assertEqual(result["status"], "telemetria_indisponivel")
        self.assertEqual(result["horizontes_aceitos"], [])
        product = json.loads((root / "assets/data/rota_fuga_santa_tereza.json").read_text(encoding="utf-8"))
        self.assertTrue(all(cell["min_ate_limiar"] is None for cell in product["quadras"]))

    def test_fresh_build_keeps_suspended_8h_unavailable(self):
        import test_rota_fuga_santa_tereza_field as fixtures
        forecast = fixtures.forecast_fixture()
        forecast["horizontes"]["8h"].update(disponivel=False, ativo_ao_vivo=False, nivel_previsto_cm=None)
        # Test clock is recorded in the temporary product, never applied to production.
        root = self.fixture(forecast, now=fixtures.NOW)
        result = validate_product(root)
        self.assertIn("2h", result["horizontes_aceitos"])
        self.assertNotIn("8h", result["horizontes_aceitos"])
        product = json.loads((root / "assets/data/rota_fuga_santa_tereza.json").read_text(encoding="utf-8"))
        self.assertIn("8h", [item["horizonte"] for item in product["meta"]["temporal"]["horizontes_rejeitados"]])

    def test_legacy_or_false_operational_status_fails(self):
        root = self.fixture()
        path = root / "assets/data/rota_fuga_santa_tereza.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for field, value in (("schema_version", None), ("status", "operacional"), ("zero_regua_m", 5.0)):
            modified = copy.deepcopy(original)
            modified["meta"][field] = value
            path.write_text(json.dumps(modified), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_product(root)

    def test_html_or_counts_tampering_fails(self):
        root = self.fixture()
        html = root / "santa_tereza_rota_fuga.html"
        original = html.read_text(encoding="utf-8")
        html.write_text(original + "inconsistent", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "HTML/JSON"):
            validate_product(root)
        html.write_text(original, encoding="utf-8")
        path = root / "assets/data/rota_fuga_santa_tereza.json"
        product = json.loads(path.read_text(encoding="utf-8"))
        product["resumo"]["limiar_na_origem"] += 1
        path.write_text(json.dumps(product), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "quadras/resumo"):
            validate_product(root)

    def test_mismatched_png_contract_fails(self):
        root = self.fixture()
        path = root / "santa_tereza_previsao_inundacao.html"
        path.write_text(path.read_text(encoding="utf-8").replace('"hand_zero_cm": 160', '"hand_zero_cm": 500'), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            validate_product(root)

    def test_source_and_artifact_feed_cannot_diverge(self):
        root = self.fixture()
        path = root / "previsao_ao_vivo.json"
        forecast = json.loads(path.read_text(encoding="utf-8"))
        forecast["telemetria_ultima_nivel_cm"] += 10
        path.write_text(json.dumps(forecast), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "feed/validade"):
            validate_product(root)

    def test_workflow_builds_without_committing_or_reactivating_models(self):
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")
        step = workflow.split("      - name: Regenerar e conferir painel de pesquisa", 1)[1].split("      - name:", 1)[0]
        self.assertIn("gerar_rota_fuga_santa_tereza.py --cenario ao_vivo", step)
        self.assertIn("test_stz_pages_route_build.py --validate-product", step)
        for forbidden in ("git push", "git commit", "sintetico", "gerar_previsao", "torch"):
            self.assertNotIn(forbidden, step)
        for path in ("scripts/santa_tereza_hand_field_contract.py", "scripts/test_stz_pages_route_build.py",
                     "codigo_python/09_rota_fuga/gerar_rota_fuga_santa_tereza.py"):
            self.assertGreaterEqual(workflow.count(path), 2)
        self.assertIn('- "Rota de fuga - Santa Tereza"', workflow)
        self.assertLess(workflow.index("--validate-product"), workflow.index("      - name: Prepare static research site"))

    def test_actual_pages_sparse_checkout_can_build_and_validate_without_test_fixtures(self):
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")
        block = re.search(r"          sparse-checkout: \|\n(.*?)          sparse-checkout-cone-mode:", workflow, re.S)
        self.assertIsNotNone(block)
        patterns = [line.strip() for line in block[1].splitlines()
                    if line.strip() and not line.strip().startswith("#")]
        with tempfile.TemporaryDirectory(prefix="stz-pages-sparse-") as folder:
            root = Path(folder)

            def git(*args):
                result = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=root,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            for name in ("scripts/test_stz_pages_route_build.py", "scripts/santa_tereza_hand_field_contract.py",
                         "codigo_python/09_rota_fuga/gerar_rota_fuga_santa_tereza.py",
                         "santa_tereza_previsao_inundacao.html", "previsao_ao_vivo.json"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            (root / "scripts/test_rota_fuga_santa_tereza_field.py").write_text("must not be imported", encoding="utf-8")
            # Generated products are tracked by the real repository; the Pages
            # packager uses git ls-files, so exercise that same requirement.
            (root / "assets/data").mkdir(parents=True)
            (root / "assets/data/rota_fuga_santa_tereza.json").write_text("old product", encoding="utf-8")
            (root / "santa_tereza_rota_fuga.html").write_text("old product", encoding="utf-8")
            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=offline-fixture", "-c", "user.email=offline@example.invalid",
                "commit", "-qm", "offline sparse contract")
            git("sparse-checkout", "set", "--no-cone", *patterns)
            self.assertFalse((root / "scripts/test_rota_fuga_santa_tereza_field.py").exists())
            for args in (("codigo_python/09_rota_fuga/gerar_rota_fuga_santa_tereza.py", "--cenario", "ao_vivo"),
                         ("scripts/test_stz_pages_route_build.py", "--validate-product")):
                result = subprocess.run([sys.executable, "-B", *args], cwd=root,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(git("diff", "--name-only").splitlines()),
                             {"assets/data/rota_fuga_santa_tereza.json", "santa_tereza_rota_fuga.html"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-product", action="store_true")
    args, remaining = parser.parse_known_args()
    if args.validate_product:
        try:
            print(json.dumps(validate_product(ROOT), ensure_ascii=False))
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
            raise SystemExit("ERRO painel de pesquisa Pages: " + str(exc)) from exc
    else:
        unittest.main(argv=[sys.argv[0], *remaining])
