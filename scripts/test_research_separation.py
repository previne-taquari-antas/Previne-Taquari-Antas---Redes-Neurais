"""Guardrails for keeping short live forecasts separate from long research."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ResearchSeparationTests(unittest.TestCase):
    def test_public_forecast_has_no_research_links(self):
        # Decisão da coordenação: as páginas de pesquisa ficam fora do caminho público por ora.
        for name in ("santa_tereza_previsao_inundacao.html", "mucum_previsao_inundacao.html"):
            self._confere(name)

    def _confere(self, name):
        html = (ROOT / name).read_text(encoding="utf-8")
        self.assertNotIn('class="research-panel', html)
        self.assertNotIn('class="research-separate-link"', html)
        self.assertNotIn("pesquisa_status", html)
        self.assertNotIn("researchRiskUrl:", html)


if __name__ == "__main__":
    unittest.main()
