"""Testes sem rede: isolamentos, limites de cota e filtro de residencias IBGE."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    s = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


rv = module("gt_risco_vida", "scripts/gt_risco_vida.py")
ibge = module("gt_cnefe_residencias", "scripts/gt_cnefe_residencias.py")


def fixture():
    # Duas margens comunicadas por rua baixa. No 2 e destino elevado.
    # Origem 0 continua seca enquanto o elo 1-2 e cortado no HAND=4.
    return {
        "meta": {
            "municipio": "Município sintético",
            "gerado_em": "teste",
            "casas_campos": ["lat", "lon", "no", "cota_alaga"],
            "nivel_projeto_m": 4.0,
            "bankfull_m": 1.6,
        },
        "nos": [[-29.0, -51.00], [-29.0, -51.001], [-29.0, -51.002]],
        "edges": [[0, 1, 0, 0, 20.0], [1, 2, 1, 0, 4.0]],
        "cota_no": [20.0, 20.0, 20.0],
        "casas": [[-29.0, -51.0, 0, 12.0]],
        "abrigos": [{"id": "abrigo_alto", "node": 2, "cota_alaga_m": 20.0}],
        "candidatos": [{"id": "refugio_candidato", "node": 0, "cota_alaga_m": 20.0}],
        "niveis": {"hand_m": [0.0, 3.0, 4.0, 5.0, 12.0]},
    }


class TestRiscoVida(unittest.TestCase):
    def test_trecho_alagado_nao_pode_entrar_na_rota(self):
        doc = fixture()
        antes = rv.rotas_secas(doc, 3.9)
        depois = rv.rotas_secas(doc, 4.0)
        self.assertTrue(antes["dist"][0] < float("inf"))
        self.assertEqual(depois["dist"][0], float("inf"))

    def test_corte_antes_da_residencia_inundar(self):
        r = rv.diagnostica(fixture())
        case = r["origens_cenario_projeto"][0]
        self.assertTrue(case["perde_acesso_antes_inundar"])
        self.assertEqual(case["primeira_perda_rede_exploratoria_hand_m"], 4.0)
        self.assertEqual(case["estado"], "somente_destino_candidato")

    def test_sem_candidatos_nao_existe_rota(self):
        doc = fixture()
        self.assertEqual(rv.rotas_secas(doc, 4.0)["dest"][0], None)
        self.assertEqual(rv.rotas_secas(doc, 4.0, candidatos=True)["dest"][0], "refugio_candidato")

    def test_dado_desconhecido_fecha_somente_na_visao_conservadora(self):
        doc = fixture()
        doc["edges"][0][4] = None
        self.assertTrue(rv.rotas_secas(doc, 3, "exploratoria")["dist"][0] < float("inf"))
        self.assertEqual(rv.rotas_secas(doc, 3, "conservadora")["dist"][0], float("inf"))

    def test_destino_inundado_e_removido(self):
        doc = fixture()
        doc["abrigos"][0]["cota_alaga_m"] = 2.0
        self.assertEqual(rv.rotas_secas(doc, 3)["sources"], 0)

    def test_extracao_html_embutido(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "painel.html"
            p.write_text("<script>const D=" + json.dumps(fixture()) + ", M=D.meta;</script>", encoding="utf-8")
            self.assertEqual(rv.carrega_painel(p)["meta"]["municipio"], "Município sintético")

    def test_origem_sem_no_fica_indeterminada(self):
        doc = fixture()
        doc["casas"][0][2] = -1
        out = rv.diagnostica(doc)
        self.assertEqual(out["origens_cenario_projeto"][0]["estado"], "sem_no_de_acesso")

    def test_zero_bloqueio_no_limite(self):
        self.assertFalse(rv.aberto(4.0, 4.0, "exploratoria"))
        self.assertTrue(rv.aberto(4.1, 4.0, "conservadora"))


class TestCnefe(unittest.TestCase):
    def test_filtra_escola_ubs_igreja_preserva_residencia_mista(self):
        a = {"COD_MUN": "4317251", "LATITUDE": "-29.16", "LONGITUDE": "-51.73",
             "NV_GEO_COORD": "1", "COD_TIPO_ESPECIE": "101"}
        rows = [
            dict(a, COD_ESPECIE="4"),
            dict(a, COD_ESPECIE="5"),
            dict(a, COD_ESPECIE="8"),
            dict(a, COD_ESPECIE="1"),
            dict(a, COD_ESPECIE="1"),
            dict(a, COD_ESPECIE="7", LATITUDE="-29.15"),
        ]
        gj, meta = ibge.pontos_residenciais(rows, "4317251")
        self.assertEqual(len(gj["features"]), 1)
        props = gj["features"][0]["properties"]
        self.assertEqual(props["unidades_domiciliares_cnefe_2022"], 2)
        self.assertEqual(props["outros_usos_no_ponto"], 3)
        self.assertEqual(meta["unidades_particulares"], 2)

    def test_nivel_geocodificacao_inferior_pede_revisao(self):
        row = {"COD_MUN": "4312609", "LATITUDE": "-29.16",
               "LONGITUDE": "-51.87", "NV_GEO_COORD": "6",
               "COD_ESPECIE": "1", "COD_TIPO_ESPECIE": "101"}
        gj, meta = ibge.pontos_residenciais([row], "4312609")
        self.assertEqual(meta["pontos_necessitam_revisao_posicional"], 1)

    def test_csv_ambas_codificacoes(self):
        s = "COD_MUN;COD_ESPECIE;LATITUDE;LONGITUDE;NV_GEO_COORD;COD_TIPO_ESPECIE\n4317251;1;-29.16;-51.73;1;101\n"
        self.assertEqual(len(list(ibge.linhas_csv(s.encode("utf-8")))), 1)
        self.assertEqual(len(list(ibge.linhas_csv(s.encode("cp1252")))), 1)


if __name__ == "__main__":
    unittest.main()
