import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "codigo_python/09_rota_fuga/preparar_cnefe_pilotos.py"
spec = importlib.util.spec_from_file_location("cnefe_pilotos", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CSV_TESTE = (
    "COD_MUN;COD_ESPECIE;LATITUDE;LONGITUDE;NV_GEO_COORD;COD_TIPO_ESPECIE\n"
    "4317251;1;-29,170;-51,730;1;101\n"
    "4317251;1;-29,170;-51,730;1;101\n"
    "4317251;4;-29,171;-51,731;1;\n"
    "4317251;5;-29,172;-51,732;1;\n"
    "4317251;8;-29,173;-51,733;1;\n"
    "4317251;2;-29,174;-51,734;2;104\n"
    "4312609;1;-29,175;-51,735;1;101\n"
    "4317251;1;;;1;101\n"
)
class FiltragemCNEFETest(unittest.TestCase):
    def test_filtra_especies_sem_transformar_ubs_em_casa(self):
        geo, cont = mod.extrair(CSV_TESTE, "4317251")
        self.assertEqual(len(geo["features"]), 1)
        self.assertEqual(geo["features"][0]["properties"]["quantidade_registros_cnefe_no_ponto"], 2)
        self.assertEqual(geo["features"][0]["properties"]["especie"], "1")
        self.assertFalse(geo["features"][0]["properties"]["ocupacao_atual_confirmada"])
        self.assertNotIn("DSC_ESTABELECIMENTO", geo["features"][0]["properties"])
        self.assertEqual(cont["outra_especie_excluida"], 4)
        self.assertEqual(cont["coordenada_invalida"], 1)
    def test_coletivo_opcional_nao_confundido_com_casa(self):
        geo, _ = mod.extrair(CSV_TESTE, "4317251", incluir_coletivos=True)
        self.assertEqual(len(geo["features"]), 2)
        self.assertEqual({x["properties"]["especie"] for x in geo["features"]}, {"1", "2"})
    def test_proximidade_nao_confirma_residencia(self):
        geo, _ = mod.extrair(CSV_TESTE, "4317251")
        p = {"meta":{"casas_campos":["lat","lon"]},"casas":[[-29.17,-51.73]]}
        resumo = mod.verificar_osm(geo, p)
        self.assertEqual(resumo["pontos_cnefe_com_osm_a_ate_20m"], 1)
        self.assertFalse(geo["features"][0]["properties"]["correspondencia_confirmada"])
    def test_parser_json_embutido(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"painel.html"
            p.write_text('var a=1; const D={"casas":[[1]],"meta":{"nome":"abc"}};')
            self.assertEqual(mod.decodificar_painel_html(p)["casas"], [[1]])
    def test_rejeita_cabecalho_invalido(self):
        with self.assertRaises(ValueError):
            mod.extrair("municipio;lat\na;b\n", "4317251")
if __name__ == "__main__":
    unittest.main()
