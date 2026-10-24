import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from vincular_cnefe_edificacoes_porto_alegre import processar


class TestVinculacao(unittest.TestCase):
    def test_esquina_nao_vira_casa_errada_e_mantem_total(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            osm={"type":"FeatureCollection","features":[
                {"type":"Feature","properties":{"osm_id":"1","building":"house","addr:street":"Rua Alfa","addr:housenumber":"10"},
                 "geometry":{"type":"Polygon","coordinates":[[[-51.2,-30.0],[-51.1998,-30.0],[-51.1998,-29.9999],[-51.2,-29.9999],[-51.2,-30.0]]]}},
                {"type":"Feature","properties":{"osm_id":"2","building":"warehouse","addr:street":"Rua Alfa","addr:housenumber":"12"},
                 "geometry":{"type":"Polygon","coordinates":[[[-51.2004,-30.0],[-51.2002,-30.0],[-51.2002,-29.9999],[-51.2004,-29.9999],[-51.2004,-30.0]]]}}]}
            (root/"osm.geojson").write_text(json.dumps(osm))
            with (root/"c.csv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["COD_UNICO_ENDERECO","COD_MUNICIPIO","COD_ESPECIE","LATITUDE","LONGITUDE","NV_GEO_COORD","NOM_TIPO_SEGLOGR","NOM_SEGLOGR","NUM_ENDERECO"],delimiter=";")
                w.writeheader()
                for num in ("10", "12", "14"):
                    w.writerow({"COD_UNICO_ENDERECO":num,"COD_MUNICIPIO":"4314902","COD_ESPECIE":"1", "LATITUDE":"-29.99995", "LONGITUDE":"-51.2001", "NV_GEO_COORD":"4", "NOM_TIPO_SEGLOGR":"Rua","NOM_SEGLOGR":"Alfa","NUM_ENDERECO":num})
            result=processar(root/"c.csv", root/"osm.geojson", root/"res")
            self.assertEqual(result["domicilios_particulares_cnefe"],3)
            self.assertEqual(result["domicilios_em_pontos_compartilhados"],3)
            self.assertTrue(result["nenhuma_correcao_confirmada_automaticamente"])
            with (root/"res/associacoes_auditoria.csv").open(encoding="utf-8-sig") as h:
                rows=list(csv.DictReader(h))
            self.assertEqual(len(rows),3)
            self.assertEqual(rows[1]["status"],"sem_edificacao_compativel")
            self.assertEqual(rows[0]["status"],"esquina_ou_aglomerado_revisar")
            self.assertTrue(all(r["lat_original"]=="-29.99995" for r in rows))

if __name__=="__main__": unittest.main()
