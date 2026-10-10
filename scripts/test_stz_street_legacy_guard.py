"""Regression tests for the blocked, unvalidated STZ house/street pipeline.

No raster generation, live inference, network downloads, or route approval.
The legacy numerical payload is retained byte-for-byte and never executed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
STREETS = ROOT / "codigo_python/09_rota_fuga"
sys.path.insert(0, str(STREETS))
import gerar_cota_alaga as threshold
import gerar_painel as panel
import gerar_rota_fuga_ruas as routes
import rede_casas as houses
from stz_street_legacy_guard import require_supported_street_pipeline

PAGE = ROOT / "santa_tereza_painel_casas.html"
PRESERVED_DATA_SHA256 = "880914d46614ab139d38e1de9228d78e4cd19eae1e002fbf421882ffb093d9ab"


class StreetGuardTests(unittest.TestCase):
    def test_santa_tereza_is_blocked_but_other_cities_are_not_recalibrated(self):
        for city in ("santa_tereza", "Santa Tereza", "4317251"):
            with self.subTest(city=city), self.assertRaisesRegex(RuntimeError, "Execução bloqueada"):
                require_supported_street_pipeline(city)
        for city in ("mucum", "Muçum", "4312609", None):
            self.assertIsNone(require_supported_street_pipeline(city))
        self.assertEqual(routes.CIDADES["mucum"]["zero_regua_m"], 5.0)

    def test_generic_entry_points_reject_stz_before_io(self):
        calls = (
            lambda: threshold.gera("santa_tereza"),
            lambda: threshold.gera_de_contornos("santa_tereza"),
            lambda: routes.nivel_de_projeto(routes.CIDADES["santa_tereza"], "live", 0),
            lambda: routes.Inundacao(routes.CIDADES["santa_tereza"]),
            lambda: panel.gera("santa_tereza"),
            lambda: houses.casas_com_rota({"meta": {"municipio": "Santa Tereza"}}),
            lambda: houses.GradeCasas({"meta": {"municipio": "Santa Tereza"}}),
        )
        with mock.patch("builtins.open", side_effect=AssertionError("must not read/write")):
            for call in calls:
                with self.subTest(call=call), self.assertRaisesRegex(RuntimeError, "NoData, saturação e MDT"):
                    call()

    def test_cli_blocks_before_level_selection_or_network(self):
        with (
            mock.patch.object(sys, "argv", ["generator", "--cidade", "santa_tereza"]),
            mock.patch.object(routes, "nivel_de_projeto", side_effect=AssertionError("must not select")),
            mock.patch.object(routes, "baixa_osm", side_effect=AssertionError("must not download")),
            self.assertRaisesRegex(RuntimeError, "Execução bloqueada"),
        ):
            routes.main()

    def test_mucum_threshold_dispatch_still_uses_its_original_branch(self):
        with (
            mock.patch.dict(routes.CIDADES, {"mucum": {"cota_de_contornos": True}}),
            mock.patch.object(threshold, "gera_de_contornos", return_value="unchanged_mucum") as dispatch,
        ):
            self.assertEqual(threshold.gera("mucum"), "unchanged_mucum")
        dispatch.assert_called_once_with("mucum")

    def test_house_payload_preserved_and_legacy_script_is_inert(self):
        source = PAGE.read_text(encoding="utf-8")
        data = re.search(r"(?m)^const D=(.*);$", source)
        self.assertIsNotNone(data)
        self.assertEqual(hashlib.sha256(data[1].encode("utf-8")).hexdigest(), PRESERVED_DATA_SHA256)
        self.assertIn('data-stz-street-contract="blocked_unvalidated"', source)
        scripts = re.findall(r"<script([^>]*)>", source)
        self.assertEqual(len(scripts), 1)
        self.assertIn('type="application/x-stz-legacy-blocked"', scripts[0])
        self.assertIn("Ausência de mancha não significa segurança", source)
        self.assertIn("Não é alerta oficial", source)
        self.assertIn('href="santa_tereza_painel_evacuacao.html"', source)
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("Exercício casa a casa · bloqueado para uso atual", index)

    def test_blocked_house_page_real_browser_no_simulation_no_overflow(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True)
            try:
                for width in (390, 1440):
                    page = browser.new_page(viewport={"width": width, "height": 1000})
                    try:
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(PAGE.as_uri(), wait_until="domcontentloaded")
                        self.assertTrue(page.locator("#stz-contract-title").is_visible())
                        self.assertFalse(page.locator("#map").is_visible())
                        self.assertFalse(page.locator(".hud").is_visible())
                        self.assertTrue(page.evaluate("typeof D === 'undefined' && typeof L === 'undefined'"))
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1)
                        self.assertEqual(errors, [])
                    finally:
                        page.close()
            finally:
                browser.close()

    def test_branding_treats_blocked_page_as_normal_flow_not_fullscreen_map(self):
        spec = importlib.util.spec_from_file_location("stz_guard_branding", ROOT / "scripts/apply_institutional_logos.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        branding = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(branding)
        structure = branding.PageStructure(PAGE.read_text(encoding="utf-8"))
        self.assertFalse(structure.fixed_map)
        self.assertIsNone(structure.cdata_elem)


if __name__ == "__main__":
    unittest.main()
