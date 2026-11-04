# -*- coding: utf-8 -*-
"""Pontos de encontro, primeira versão (codigo_python/09_rota_fuga/pontos_encontro.py e
pontos_encontro.html): trecho de via fora da mancha do mapa único com 100 m de afastamento.

Sem o arquivo do MUP RS no checkout, a conta roda numa mancha de teste (a cheia de set/2023 do
painel de Santa Tereza): o que se testa é o critério, não o resultado publicado.

  python tests/test_pontos_encontro.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "codigo_python" / "09_rota_fuga"))
try:
    from shapely.geometry import Point, Polygon, mapping, shape
    from shapely.ops import unary_union
    import pontos_encontro as pe
except ImportError:  # CI sem shapely
    pe = None
import locais_altos  # noqa: E402

PAGINA = (RAIZ / "pontos_encontro.html").read_text(encoding="utf-8")


def mancha_de_teste(destino):
    """A mancha HAND de set/2023 do painel de Santa Tereza, só para exercitar o critério."""
    d = locais_altos.payload(RAIZ / "santa_tereza_painel_casas.html")
    pol = [Polygon([(lo, la) for la, lo in p[0]], [[(lo, la) for la, lo in h] for h in p[1:]]).buffer(0)
           for p in d["altos"]["mancha_cheia"]["poligonos"]]
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": mapping(unary_union(pol))}]}, f)


@unittest.skipIf(pe is None, "sem shapely")
class CriterioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.arq = os.path.join(cls.tmp.name, "mancha.geojson")
        mancha_de_teste(cls.arq)
        cls.d = pe.documento("santa_tereza", cls.arq)
        cls.doc = locais_altos.payload(pe.CIDADES["santa_tereza"]["painel"])
        cls.plano = pe.Plano(cls.doc["nos"])
        cls.mancha = pe.le_mancha(cls.arq, cls.plano)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pontos_ficam_fora_da_faixa_e_numa_via_fora_dela(self):
        self.assertTrue(self.d["pontos"])
        seguras = {k for a, b, ok in self.d["arestas"] if ok for k in (a, b)}
        for p in self.d["pontos"]:
            dist = self.mancha.distance(Point(self.plano.xy(p["lat"], p["lon"])))
            self.assertGreater(dist, pe.OFFSET_M, p)           # a mais de 100 m da mancha
            self.assertIn(p["no"], seguras, p)                  # ponta de um trecho de via inteiro fora da faixa
            self.assertAlmostEqual(dist, p["dist_mancha_m"], delta=0.1)

    def test_trecho_seguro_nao_toca_a_faixa(self):
        from shapely.geometry import LineString
        zona = self.mancha.buffer(pe.OFFSET_M)
        nos = self.d["nos"]
        for a, b, ok in self.d["arestas"]:
            if ok:
                self.assertFalse(zona.intersects(LineString([self.plano.xy(*nos[a]), self.plano.xy(*nos[b])])))

    def test_casa_na_mancha_ou_na_faixa_tem_caminho_ate_o_ponto(self):
        F = {k: i for i, k in enumerate(self.d["casas_campos"])}
        com_rota = 0
        for c in self.d["casas"]:
            est = self.d["estados"][c[F["estado"]]]
            if est == "fora":
                self.assertEqual(c[F["ponto"]], -1)
                self.assertFalse(self.mancha.buffer(pe.OFFSET_M).contains(Point(self.plano.xy(c[F["lat"]], c[F["lon"]]))))
            elif c[F["ponto"]] >= 0:
                com_rota += 1
                self.assertLessEqual(c[F["tempo_s"]], pe.TEMPO_TETO_S)
        self.assertGreater(com_rota, 0)
        # todo nó com ponto segue o "prox" até o próprio ponto
        alvo = {p["no"]: i for i, p in enumerate(self.d["pontos"])}
        for n, k in enumerate(self.d["ponto_no"]):
            if k < 0:
                continue
            j, g = n, 0
            while self.d["prox"][j] >= 0 and g < 6000:
                j, g = self.d["prox"][j], g + 1
            self.assertEqual(alvo.get(j), k)

    def test_afastamento_maior_afasta_os_pontos(self):
        d2 = pe.documento("santa_tereza", self.arq, offset_m=200.0)
        self.assertEqual(d2["offset_m"], 200.0)
        for p in d2["pontos"]:
            self.assertGreater(self.mancha.distance(Point(self.plano.xy(p["lat"], p["lon"]))), 200.0)

    def test_deterministico(self):
        self.assertEqual(json.dumps(self.d, sort_keys=True), json.dumps(pe.documento("santa_tereza", self.arq), sort_keys=True))

    def test_publicado_bate_com_a_conta(self):
        for cidade, versao in [(c, v) for c in pe.CIDADES for v in pe.VERSOES]:
            pub, mancha = Path(pe.saida_padrao(cidade, versao)), Path(pe.mancha_padrao(cidade, versao))
            if not pub.exists():
                continue
            self.assertTrue(mancha.exists(), f"{pub.name} sem a mancha de origem")
            d = json.loads(pub.read_text(encoding="utf-8"))
            self.assertEqual(d["versao"], versao)
            self.assertEqual(d["mancha_sha256"], pe._sha256(mancha))
            somada = pe.mancha_somada(cidade, versao)
            if somada:  # o mapa único soma a maior cheia do modelo (set/2023 em Santa Tereza)
                self.assertEqual(d["mancha_somada"]["sha256"], pe._sha256(somada))
            if d.get("criterios") in ("v2", "v3"):
                self.assertEqual(d["osm_encontro"]["sha256"], pe._sha256(pe.osm_encontro(cidade)))
            padrao = d.get("plano", {}).get("padrao", {"tempo_max_min": pe.TEMPO_SUGERIDO_MIN, "modo": "algoritmo"})
            novo = pe.documento(cidade, None, d["offset_m"], d["fonte_mancha"], versao, d.get("criterios", "v1"),
                                padrao["tempo_max_min"], padrao["modo"])
            # a conta (pontos, casas, ruas) bate exatamente; o contorno desenhado da faixa varia nos últimos
            # dígitos entre versões do GEOS (vértices dos arcos do buffer)
            for k in d:
                if k in ("mancha", "faixa"):
                    a, b = shape(d[k]), shape(novo[k])
                    self.assertLess(a.symmetric_difference(b).area, 1e-3 * b.area, (cidade, k))
                else:
                    self.assertEqual(json.dumps(d[k], sort_keys=True), json.dumps(novo[k], sort_keys=True), (cidade, k))


@unittest.skipIf(pe is None, "sem shapely")
class CriteriosV2Test(unittest.TestCase):
    """Versão 2: passa carro, longe de deslizamento e preferência por lugar de reunião."""

    def test_pontos_publicados_cumprem_os_criterios(self):
        with open(pe.DESLIZAMENTOS, encoding="utf-8") as f:
            desl = [shape(ft["geometry"]).buffer(0) for ft in json.load(f)["features"]]
        for cidade, versao in [(c, v) for c in pe.CIDADES for v in pe.VERSOES]:
            pub = Path(pe.saida_padrao(cidade, versao))
            if not pub.exists():
                continue
            d = json.loads(pub.read_text(encoding="utf-8"))
            if d.get("criterios") not in ("v2", "v3"):
                continue
            plano = pe.Plano(d["nos"])
            perto = unary_union([g for g in desl if g.distance(Point(d["pontos"][0]["lon"], d["pontos"][0]["lat"])) < 0.1])
            for p in d["pontos"]:
                self.assertIn(p["via"], pe.VIAS_CARRO, (cidade, versao, p["id"]))
                xy = Point(plano.xy(p["lat"], p["lon"]))
                dist = plano.de_lonlat(perto).distance(xy) if not perto.is_empty else float("inf")
                self.assertGreater(dist, pe.DESLIZAMENTO_M, (cidade, versao, p["id"]))
                self.assertAlmostEqual(dist, p["dist_deslizamento_m"], delta=1.0)
                if p["lugar"]:
                    self.assertLessEqual(p["lugar"]["dist_m"], pe.LUGAR_M)
            s = d["resumo"]["filtro"]
            self.assertGreaterEqual(s["candidatos_v1"], s["com_carro"])
            self.assertGreaterEqual(s["com_carro"], s["longe_de_deslizamento"])

    def test_v1_continua_reproduzivel(self):
        d1 = pe.documento("santa_tereza", pe.mancha_padrao("santa_tereza", "mup"), criterios="v1")
        self.assertEqual(d1["criterios"], "v1")
        self.assertNotIn("via", d1["pontos"][0])
        self.assertEqual(len(d1["pontos"]), 6)  # a primeira versão publicada (#291)


@unittest.skipIf(pe is None, "sem shapely")
class PlanoTest(unittest.TestCase):
    """Versão 3: menos pontos que levam as casas a um ponto dentro do tempo máximo (sugerido: 20 min)."""

    @classmethod
    def setUpClass(cls):
        cls.pub = {}
        for cidade, versao in [(c, v) for c in pe.CIDADES for v in pe.VERSOES]:
            caminho = Path(pe.saida_padrao(cidade, versao))
            if caminho.exists():
                d = json.loads(caminho.read_text(encoding="utf-8"))
                if d.get("criterios") == "v3":
                    cls.pub[(cidade, versao)] = d

    def test_padrao_e_o_tempo_sugerido(self):
        self.assertEqual(pe.TEMPO_SUGERIDO_MIN, 20)
        for k, d in self.pub.items():
            self.assertEqual(d["plano"]["padrao"], {"tempo_max_min": 20, "modo": "algoritmo"}, k)
            self.assertIn("20 min", d["criterio"])

    def test_cobre_tudo_o_que_da_e_nao_sobra_ponto(self):
        import plano_pontos
        for k, d in self.pub.items():
            rede, teto = d["plano"], 20 * 600
            r = plano_pontos.planeja(rede, 20, "algoritmo")
            res = r["resumo"]
            # toda casa que alcança algum candidato em 20 min chega a um ponto escolhido em 20 min
            self.assertEqual(res["no_limite"] + res["sem_ponto_possivel"], res["precisam"], k)
            self.assertEqual(res["fora_dos_escolhidos"], 0, k)
            # plano + algoritmo também cobre todas (o oficial vem primeiro só para quem chega a ele no tempo)
            r2 = plano_pontos.planeja(rede, 20, "plano+algoritmo")
            self.assertEqual(r2["resumo"]["fora_dos_escolhidos"], 0, k)
            seg = len({o["no"] for o in rede["oficiais"] if o["seguro"]})
            for i, c in enumerate(r2["casas"]):
                if c[4] == 1:  # foi ao ponto oficial: chega nele no tempo
                    self.assertLess(c[0], seg)
                    self.assertLessEqual(c[1], teto)
            # nenhum ponto sobra: cada um é o único a até 20 min de pelo menos uma casa
            for j, p in enumerate(r["pontos"]):
                self.assertTrue(any(c[0] == j and c[3] == 1 and c[1] <= teto for c in r["casas"]), (k, p))
            self.assertLessEqual(len(r["pontos"]), plano_pontos.PONTOS_MAX)

    def test_modo_plano_so_usa_pontos_oficiais_fora_da_area_insegura(self):
        import plano_pontos
        for k, d in self.pub.items():
            r = plano_pontos.planeja(d["plano"], 20, "plano")
            seguros = [o for o in d["plano"]["oficiais"] if o["seguro"]]
            self.assertEqual([p["no"] for p in r["pontos"]], [o["no"] for o in seguros], k)
            r2 = plano_pontos.planeja(d["plano"], 20, "plano+algoritmo")
            self.assertEqual([p["no"] for p in r2["pontos"][:len(seguros)]], [o["no"] for o in seguros], k)
            self.assertGreaterEqual(r2["resumo"]["no_limite"], r["resumo"]["no_limite"], k)

    def test_nenhum_ponto_na_cheia_do_modelo(self):
        """O mapa único é de 2024; os pontos também ficam fora da maior cheia do modelo (set/2023 em Santa Tereza)."""
        for (cidade, versao), d in self.pub.items():
            fc = json.loads(Path(pe.DADOS, f"hand_maior_cheia_{cidade}.geojson").read_text(encoding="utf-8"))
            cheia = unary_union([shape(f["geometry"]) for f in fc["features"]])
            for p in d["pontos"]:
                self.assertFalse(cheia.contains(Point(p["lon"], p["lat"])), (cidade, versao, p["id"]))

    def test_nenhum_ponto_vira_ilha(self):
        """Do ponto, as ruas fora da mancha levam para fora da cidade (saída seca)."""
        for (cidade, versao), d in self.pub.items():
            doc = locais_altos.payload(pe.CIDADES[cidade]["painel"])
            plano = pe.Plano(doc["nos"])
            xy = [plano.xy(la, lo) for la, lo in doc["nos"]]
            somada = pe.mancha_somada(cidade, versao)
            mancha = pe.le_mancha([pe.mancha_padrao(cidade, versao)] + ([somada] if somada else []), plano)
            sai = pe.saida_seca(doc, xy, mancha)
            for p in d["pontos"]:
                self.assertTrue(sai[p["no"]], (cidade, versao, p["id"]))
            for o in d["plano"]["oficiais"]:
                if o["seguro"]:
                    self.assertTrue(sai[o["no"]], (cidade, versao, o["nome"]))

    def test_tempo_em_minutos_inteiros(self):
        import plano_pontos
        d = next(iter(self.pub.values()), None)
        if d is None:
            self.skipTest("sem JSON")
        with self.assertRaises(ValueError):
            plano_pontos.planeja(d["plano"], 19.5, "algoritmo")

    def test_mais_tempo_nao_pede_mais_casas_fora(self):
        import plano_pontos
        d = self.pub.get(("santa_tereza", "hand"))
        if d is None:
            self.skipTest("sem o JSON de Santa Tereza")
        fora = [plano_pontos.planeja(d["plano"], t, "algoritmo")["resumo"]["sem_ponto_possivel"] for t in (10, 20, 30, 45)]
        self.assertEqual(fora, sorted(fora, reverse=True))


@unittest.skipIf(pe is None or shutil.which("node") is None, "sem shapely ou sem node")
class PlanoParidadeTest(unittest.TestCase):
    """A página refaz a conta no navegador (assets/js/pontos_plano.js): tem de dar o mesmo que o Python."""

    def test_python_e_navegador_iguais(self):
        import plano_pontos
        js = RAIZ / "assets" / "js" / "pontos_plano.js"
        for cidade, versao in [(c, v) for c in pe.CIDADES for v in pe.VERSOES]:
            caminho = Path(pe.saida_padrao(cidade, versao))
            if not caminho.exists():
                continue
            d = json.loads(caminho.read_text(encoding="utf-8"))
            if d.get("criterios") != "v3":
                continue
            casos = [(t, m) for t in (10, 20, 35) for m in plano_pontos.MODOS]
            script = ("const P=require(process.argv[1]),fs=require('fs');const d=JSON.parse(fs.readFileSync(process.argv[2]));"
                      "const casos=JSON.parse(process.argv[3]);"
                      "process.stdout.write(JSON.stringify(casos.map(([t,m])=>P.planeja(d.plano,t,m))));")
            saida = subprocess.run(["node", "-e", script, str(js), str(caminho), json.dumps(casos)],
                                   capture_output=True, text=True, check=True).stdout
            for (t, m), r_js in zip(casos, json.loads(saida)):
                r_py = json.loads(json.dumps(plano_pontos.planeja(d["plano"], t, m)))
                self.assertEqual(r_py, r_js, (cidade, versao, t, m))
            # e o publicado é o padrão
            r = plano_pontos.planeja(d["plano"], 20, "algoritmo")
            self.assertEqual([p["no"] for p in r["pontos"]], [p["no"] for p in d["pontos"]], (cidade, versao))
            self.assertEqual(r["ponto_no"], d["ponto_no"])
            self.assertEqual(r["prox"], d["prox"])


class VersaoHandTest(unittest.TestCase):
    """Versão provisória com o modelo HAND do projeto, na maior cheia registrada de cada cidade."""

    def test_mancha_hand_no_nivel_da_maior_cheia(self):
        esperado = {"santa_tereza": ("set/2023", 23.65, 22.1), "mucum": ("mai/2024", 25.51, 20.6)}
        for cidade, (cheia, regua, contorno) in esperado.items():
            caminho = RAIZ / "assets" / "data" / "rota_fuga" / f"hand_maior_cheia_{cidade}.geojson"
            if not caminho.exists():
                continue
            pr = json.loads(caminho.read_text(encoding="utf-8"))["features"][0]["properties"]
            self.assertEqual((pr["cheia"], pr["regua_m"], pr["nivel_contorno_m"]), (cheia, regua, contorno))
            # o contorno é o primeiro nível de 0,1 m que cobre a cheia (régua - zero)
            self.assertGreaterEqual(pr["nivel_contorno_m"] + 1e-9, pr["regua_m"] - pr["zero_regua_m"])
            self.assertLess(pr["nivel_contorno_m"] - (pr["regua_m"] - pr["zero_regua_m"]), 0.1)

    @unittest.skipIf(pe is None, "sem shapely")
    def test_textos_da_versao(self):
        for cidade in pe.CIDADES:
            for versao, v in pe.VERSOES.items():
                self.assertTrue(v["evento"][cidade] and v["evento_curto"][cidade] and v["fonte"][cidade])
        self.assertFalse(pe.VERSOES["hand"]["observada"])  # a página não chama o modelo de "área atingida"
        self.assertIn("modelada", pe.VERSOES["hand"]["aviso"])


class PaginaTest(unittest.TestCase):
    def test_le_o_json_da_cidade_e_avisa(self):
        self.assertIn("'assets/data/rota_fuga/'+CID+'_pontos_encontro_'+VER+'.json'", PAGINA)
        self.assertIn("OPC.includes(qs.get('mancha'))?qs.get('mancha'):OPC[0]", PAGINA)  # versão fora da lista não monta caminho
        self.assertIn("santa_tereza:['hand']", PAGINA)  # Santa Tereza usa só a mancha do site (set/2023)
        self.assertIn("CIDADES[pedido]?pedido:'santa_tereza'", PAGINA)  # cidade fora da lista não monta caminho
        self.assertIn('<a href="tel:199">199</a>', PAGINA)
        self.assertIn("não é abrigo oficial", PAGINA)
        self.assertIn("Mapa Único do Plano Rio Grande", PAGINA)
        self.assertIn("D.mancha_observada?'área atingida em ':'cheia de '", PAGINA)
        self.assertIn("if(!casa&&bd>LONGE_DA_RUA_M)", PAGINA)  # toque longe da rua não vira rota
        self.assertNotIn("você já está fora da área atingida", PAGINA)
        self.assertIn("map.getPane('agua').style.pointerEvents='none'", PAGINA)  # a mancha não captura o toque
        self.assertIn("function local(p,sep)", PAGINA)  # versão 2: lugar, carro e deslizamento na lista e no popup
        self.assertIn('src="assets/js/pontos_plano.js"', PAGINA)  # versão 3: a página refaz o plano no navegador
        self.assertIn("PontosPlano.planeja(", PAGINA)
        self.assertIn("relatorio_por_casa", PAGINA)
        self.assertIn("s=D.plano?D.plano.casas[casa.i][0]:-1", PAGINA)  # toque na casa usa o mesmo nó do relatório
        self.assertIn("ds<=T*600", PAGINA)  # o relatório compara o tempo exato, não o arredondado


if __name__ == "__main__":
    unittest.main()
