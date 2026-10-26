#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes do painel casa a casa: cheias registradas, capacidade e abrigos.

Sem shapely/rasterio: lê o template do código-fonte e os dados embutidos nos
painéis publicados. Cobrem a revisão de out/2026:
  - painel publicado igual ao template atual (Muçum tinha ficado para trás);
  - cheias de referência batendo com os picos das séries das réguas;
  - subida padrão de 90 cm/h (40 cm/h dava margem 2 a 5 vezes maior);
  - capacidade planejada de Muçum vinda do Plano de Contingência;
  - pontos de Muçum em abrigos.geojson (sem eles o gerador abortava);
  - locais altos de Santa Tereza (out/2026): o que ficou fora da mancha de
    set/2023, a maior cheia registrada, pelo menos 2 m acima da água no MDT; o
    painel publicado é o recálculo de locais_altos.py;
  - terceira revisão (out/2026): acesso da casa no corte, margem pelo erro perigoso
    do HAND do painel, saídas pela Estrada do Vinho, pontos longe de deslizamento,
    "agora" só com o caminho ainda seco, JSON embutido sem "</".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GERADOR = RAIZ / "codigo_python" / "09_rota_fuga" / "gerar_painel.py"
PAINEIS = {"santa_tereza": RAIZ / "santa_tereza_painel_casas.html",
           "mucum": RAIZ / "mucum_painel_casas.html"}
SERIES = {"santa_tereza": RAIZ / "assets" / "data" / "eventos_analise.json",
          "mucum": RAIZ / "assets" / "data" / "mucum_eventos_analise.json"}
PLANO_MUCUM = RAIZ / "assets" / "data" / "mucum_contingencia_202607.json"
ABRIGOS = RAIZ / "assets" / "data" / "servicos" / "abrigos.geojson"
sys.path.insert(0, str(RAIZ / "codigo_python" / "09_rota_fuga"))
import locais_altos  # noqa: E402


def ler(p):
    return json.loads(p.read_text(encoding="utf-8"))


def payload_bruto(html):
    i = html.index("const D=") + len("const D=")
    return html[i:json.JSONDecoder().raw_decode(html, i)[1]]


TEMPLATE = re.search(r'_TEMPLATE = r"""(.*?)"""', GERADOR.read_text(encoding="utf-8"), re.S).group(1)
HTML = {c: p.read_text(encoding="utf-8") for c, p in PAINEIS.items()}
DADOS = {c: json.loads(payload_bruto(h)) for c, h in HTML.items()}


class PainelPublicadoTest(unittest.TestCase):
    def test_painel_e_o_template_atual(self):
        for c, html in HTML.items():
            with self.subTest(cidade=c):
                self.assertEqual(TEMPLATE.replace("__DADOS__", payload_bruto(html)), html)

    def test_subida_padrao_90(self):
        for c, d in DADOS.items():
            with self.subTest(cidade=c):
                self.assertEqual(d["meta"]["taxa_cm_h"], 90.0)

    def test_cheias_batem_com_a_serie_da_regua(self):
        for c, d in DADOS.items():
            picos = {e["pico_data"]: e["pico_cm"] / 100 for e in ler(SERIES[c])["eventos"]}
            cheias = d["meta"]["cheias_ref"]
            self.assertEqual(sum(1 for x in cheias if x.get("tipo") == "cota_oficial"), 1)
            for x in cheias:
                data = x.get("data") or ""
                if len(data) == 10:
                    with self.subTest(cidade=c, cheia=x["rotulo"]):
                        self.assertAlmostEqual(x["regua_m"], picos[data], places=2)

    def test_cheia_mais_alta_alaga_o_ginasio(self):
        d = DADOS["santa_tereza"]
        zr, pior = d["meta"]["bankfull_m"], max(x["regua_m"] for x in d["meta"]["cheias_ref"])
        gin = d["abrigos"][0]
        self.assertLessEqual(gin["cota_alaga_m"], pior - zr)

    def test_capacidade_de_muçum_do_plano(self):
        plano = ler(PLANO_MUCUM)
        por_id = {a["id"]: a for a in plano["abrigos"] + plano["pontos_encontro"]}
        for a in DADOS["mucum"]["abrigos"]:
            cap, ref = a["capacidade_plano"], por_id[a["id"]]
            vals = [v for v in (ref.get("capacidade_planejada"), ref.get("capacidade_quadro_13"),
                                ref.get("capacidade_ficha_tecnica")) if v is not None]
            with self.subTest(abrigo=a["id"]):
                self.assertEqual((cap["min"], cap["max"]), (min(vals), max(vals)))
        self.assertTrue(all(a["capacidade_plano"] is None for a in DADOS["santa_tereza"]["abrigos"]))


class LocaisAltosTest(unittest.TestCase):
    """Santa Tereza: locais altos sugeridos e cheias de referência."""

    @classmethod
    def setUpClass(cls):
        cls.d = DADOS["santa_tereza"]
        cls.alt = cls.d["altos"]
        cls.crit = cls.alt["meta"]["criterios"]
        cls.A = {k: i for i, k in enumerate(cls.alt["meta"]["casas_campos"])}

    def test_publicado_e_o_recalculo(self):
        novo = locais_altos.calcula(json.loads(payload_bruto(HTML["santa_tereza"])),
                                    self.alt["mancha_cheia"], "santa_tereza")
        for k, v in novo.items():
            with self.subTest(campo=k):
                if k == "terreno":  # PNG: compara as classes, não os bytes (variam com a versão do Pillow)
                    self.assertTrue((locais_altos.classes_do_png(v["png"]) ==
                                     locais_altos.classes_do_png(self.alt[k]["png"])).all())
                    v = {kk: vv for kk, vv in v.items() if kk != "png"}
                    self.assertEqual(json.loads(json.dumps(v)), {kk: vv for kk, vv in self.alt[k].items() if kk != "png"})
                else:
                    self.assertEqual(json.loads(json.dumps(v)), self.alt[k])

    def test_criterios_da_validacao_de_campo(self):
        ch = self.alt["meta"]["cheia"]
        self.assertAlmostEqual(ch["regua_m"] - ch["zero_regua_m"], ch["hand_m"], places=2)
        # a folga cobre o erro do terreno de 10 m: o limite H003 (a água chegou lá) fica 1,23 m acima
        # do nível no LiDAR; com folga de 1 m ele seria "alto"
        te = self.alt["meta"]["terreno_erro"]
        self.assertGreater(self.crit["acima_agua_min_m"], te["h003_acima_do_nivel_m"])
        self.assertGreater(self.crit["acima_agua_min_m"], te["lidar10_menos_rtk_max_m"])
        self.assertAlmostEqual(self.crit["celula_hand_min_m"], ch["hand_m"] + self.crit["acima_agua_min_m"], places=2)
        self.assertAlmostEqual(self.crit["celula_altitude_min_m"], ch["agua_max_rtk_m"] + self.crit["acima_agua_min_m"], places=2)

    def test_borda_da_mancha_no_mdt_bate_com_a_agua_medida(self):
        # nível da água tirado do MDT na borda da mancha, nas ruas: na faixa medida com RTK (74,1–76,5 m),
        # com a tolerância do LiDAR de 10 m (NMAD 0,71 m)
        nmad = self.alt["meta"]["terreno_erro"]["lidar10_menos_rtk_nmad_m"]
        self.assertTrue(74.1 - nmad <= self.alt["terreno"]["agua_borda_m"]["mediana"] <= self.alt["meta"]["cheia"]["agua_max_rtk_m"] + nmad)

    def test_locais_ficam_fora_da_mancha_e_acima_da_agua(self):
        self.assertTrue(2 <= len(self.alt["locais"]) <= locais_altos.LOCAIS_MAX)
        classe = locais_altos.amostrador(self.alt["terreno"])
        ch = self.alt["meta"]["cheia"]
        for loc in self.alt["locais"]:
            with self.subTest(local=loc["id"]):
                self.assertEqual(classe(loc["lat"], loc["lon"]), "alto")
                self.assertGreaterEqual(loc["acima_agua_m"], self.crit["acima_agua_min_local_m"])
                self.assertAlmostEqual(loc["altitude_m"] - loc["agua_m"], loc["acima_agua_m"], delta=0.11)
                self.assertGreaterEqual(loc["agua_m"], round(ch["agua_max_rtk_m"], 1))  # nunca abaixo da água medida
                self.assertEqual(self.alt["no_alto"][loc["no"]], 1)
                self.assertGreater(loc["n_casas"], 0)

    def test_terreno_alto_coerente_com_os_nos(self):
        classe = locais_altos.amostrador(self.alt["terreno"])
        hand = self.alt["meta"]["nivel_mancha_m"]  # o mesmo nível do contorno desenhado
        for k, (la, lo) in enumerate(self.d["nos"]):
            c = self.d["cota_no"][k]
            # alto no mapa e com a folga também pelo HAND <=> nó alto (o HAND manda na borda da mancha)
            self.assertEqual(classe(la, lo) == "alto" and (c is None or c >= self.crit["celula_hand_min_m"]),
                             bool(self.alt["no_alto"][k]))
        F = {k: i for i, k in enumerate(self.d["meta"]["casas_campos"])}
        for ci, c in enumerate(self.alt["casas"]):
            cota = self.d["casas"][ci][F["cota_alaga"]]
            if cota is not None and cota <= hand:
                self.assertEqual(self.alt["meta"]["classes_terreno"][c[self.A["terreno"]]], "dentro")
        areas = self.alt["terreno"]["area_ha"]
        self.assertGreater(areas["alto"], 0)
        self.assertGreater(areas["abaixo_da_agua"], 0)
        # casa "no alto" tem a folga também pelo HAND (8 casas com HAND 23,2–24,1 diziam "não precisa sair")
        for ci, c in enumerate(self.alt["casas"]):
            if self.alt["meta"]["estados"][c[self.A["estado"]]] == "no_alto":
                cota = self.d["casas"][ci][F["cota_alaga"]]
                self.assertTrue(cota is None or cota >= self.crit["celula_hand_min_m"], ci)

    def test_rotas_pela_rede_e_corte_coerente(self):
        A, cota = self.A, self.d["cota_no"]
        aresta = {}
        for a, b, _ag, _pe, cz in self.d["edges"]:
            for k in ((a, b), (b, a)):
                aresta[k] = max(aresta.get(k, -1), 1e9 if cz is None else cz)
        n_rota = 0
        for ci, c in enumerate(self.alt["casas"]):
            if self.alt["meta"]["estados"][c[A["estado"]]] != "rota":
                continue
            n_rota += 1
            r = c[A["rota"]]
            with self.subTest(casa=ci):
                F = {k: i for i, k in enumerate(self.d["meta"]["casas_campos"])}
                casa = self.d["casas"][ci]
                # outra margem (sem caminho até o abrigo oficial): parte do nó mais perto do pé da perpendicular
                no = casa[F["no"]] if casa[F["no"]] >= 0 else locais_altos.no_mais_proximo(
                    self.d["nos"], (casa[F["proj_lat"]], casa[F["proj_lon"]]))
                self.assertEqual(r[0], no)
                if c[A["local"]] >= 0:
                    self.assertEqual(r[-1], self.alt["locais"][c[A["local"]]]["no"])
                else:  # nenhum ponto sugerido ao alcance: vai ao terreno alto mais perto
                    self.assertEqual(self.alt["no_alto"][r[-1]], 1)
                self.assertTrue(all((u, v) in aresta for u, v in zip(r, r[1:])))
                # o acesso da casa até a rua também corta o caminho (antes ficava de fora: 41 casas
                # recebiam "quando sair" até 2 m alto)
                ac = self.d["acesso_cota"][ci]
                cortes = [aresta[(u, v)] for u, v in zip(r, r[1:])] + [1e9 if cota[k] is None else cota[k] for k in r] + \
                         [1e9 if ac is None else ac]
                esperado = min(cortes)
                self.assertEqual(c[A["corte_m"]], None if esperado >= 1e9 else round(esperado, 1))
        self.assertGreater(n_rota, 100)

    def test_outra_margem_tem_caminho(self):
        # casas sem caminho até o abrigo oficial, mas com rua: antes ficavam "sem via"
        F = {k: i for i, k in enumerate(self.d["meta"]["casas_campos"])}
        sem_oficial = [ci for ci, c in enumerate(self.d["casas"]) if c[F["no"]] < 0 and c[F["proj_lat"]] is not None]
        self.assertGreater(len(sem_oficial), 10)
        estados = self.alt["meta"]["estados"]
        sem_via = [ci for ci in sem_oficial if estados[self.alt["casas"][ci][self.A["estado"]]] == "sem_via"]
        self.assertEqual(sem_via, [])

    def test_ilhas_e_alternativa_ligada(self):
        nm, A = self.alt["meta"]["nivel_mancha_m"], self.A
        ilhados = [l for l in self.alt["locais"] if l["ilha_m"] is not None and l["ilha_m"] <= nm]
        self.assertTrue(ilhados)  # o centro (ESF, igreja) vira ilha antes de uma cheia como a de 2023
        for ci, c in enumerate(self.alt["casas"]):
            j = c[A["alt_local"]]
            if j is None:
                continue
            with self.subTest(casa=ci):
                il = self.alt["locais"][j]["ilha_m"]
                self.assertTrue(il is None or il > nm)  # a alternativa não fica ilhada
                self.assertGreaterEqual(c[A["alt_tempo_s"]], c[A["tempo_s"]])
                self.assertLessEqual(c[A["alt_tempo_s"]], min(c[A["tempo_s"]] + locais_altos.ALT_EXTRA_MAX_S,
                                                              locais_altos.ALT_TOTAL_MAX_S))
                self.assertIn(c[A["ilha_m"]], [l["ilha_m"] for l in ilhados])
                # a alternativa tem traçado e nível de saída próprios
                ra = c[A["alt_rota"]]
                self.assertEqual(ra[0], c[A["rota"]][0])
                self.assertEqual(ra[-1], self.alt["locais"][j]["no"])
                self.assertTrue(c[A["alt_corte_m"]] is None or c[A["alt_corte_m"]] <= (self.d["acesso_cota"][ci] or 1e9))
        self.assertEqual(len(self.alt["margem_nos"]), len(self.d["nos"]))
        # casas no alto ilhadas: tempo até passar o gargalo, para o aviso de quem depende de remédio
        com_tempo = [c for c in self.alt["casas"] if c[A["ilha_tempo_s"]] is not None]
        self.assertTrue(com_tempo)
        self.assertTrue(all(self.alt["meta"]["estados"][c[A["estado"]]] == "no_alto" and 0 <= c[A["ilha_m"]] <= nm
                            for c in com_tempo))

    def test_estrada_do_vinho_e_saida_da_cidade(self):
        # a rede corta a Estrada do Vinho a 600 m da borda; sem ela, o ponto na própria estrada "virava ilha"
        vinho = [l for l in self.alt["locais"] if l["rua"] == "Estrada do Vinho"]
        self.assertTrue(vinho)
        self.assertTrue(all(l["ilha_m"] is None for l in vinho))
        self.assertGreater(len(self.alt["meta"]["saidas"]), 3)

    def test_pontos_longe_de_deslizamento_e_altos_no_entorno(self):
        cic = locais_altos.cicatrizes(str(RAIZ / self.alt["meta"]["cicatrizes"]), locais_altos.recorte(self.d["nos"]))
        self.assertTrue(cic)
        for loc in self.alt["locais"]:
            with self.subTest(local=loc["id"]):
                self.assertGreater(locais_altos.dist_cicatriz((loc["lat"], loc["lon"]), cic), locais_altos.CICATRIZ_MIN_M)
                self.assertIsNotNone(loc["encosta_graus"])

    def test_margem_cobre_o_erro_perigoso_do_hand_do_painel(self):
        ch = self.alt["meta"]["cheia"]
        # as métricas do artigo são do HAND krigado; o painel usa o HAND D8 de 5 m
        self.assertGreaterEqual(self.alt["meta"]["margem_corte_m"], ch["hand_painel"]["erro_max_perigoso_m"])
        self.assertIn("hand_krigado_artigo", ch)
        # pelo centro do pixel, a borda da mancha fica abaixo da maior água medida (antes, a mancha
        # inflada pelo contorno do PIL punha a mediana acima dela)
        self.assertLess(self.alt["terreno"]["agua_borda_m"]["mediana"], ch["agua_max_rtk_m"])

    def test_acesso_bate_com_os_contornos(self):
        contornos = RAIZ / "assets" / "data" / "santa_tereza_inundacao" / "contornos_mancha.json"
        try:
            import gerar_painel
        except ImportError:
            self.skipTest("sem shapely (CI enxuto)")
        if not contornos.exists():
            self.skipTest("sem contornos_mancha.json no checkout")
        self.assertEqual(gerar_painel.cota_acesso("santa_tereza", json.loads(payload_bruto(HTML["santa_tereza"]))),
                         self.d["acesso_cota"])

    def test_referencias_dizem_se_alagaram(self):
        classes = set(self.alt["meta"]["classes_terreno"])
        for loc in self.alt["locais"]:
            for p in loc["perto"]:
                self.assertIn(p["terreno"], classes)

    def test_aviso_de_estudo_enquanto_a_mancha_for_legada(self):
        self.assertTrue(self.d["meta"]["aviso_estudo"])
        self.assertIsNone(DADOS["mucum"]["meta"].get("aviso_estudo"))

    def test_pagina_paralela_usa_os_dados_do_painel(self):
        pag = ler(RAIZ / "assets" / "data" / "rota_fuga" / "santa_tereza_rotas_altas_set2023.json")
        self.assertEqual(pag, json.loads(json.dumps(locais_altos.pagina_rotas_altas(self.d))))
        html = (RAIZ / "santa_tereza_rotas_altas_set2023.html").read_text(encoding="utf-8")
        self.assertIn(pag["schema_version"], html)
        self.assertNotIn("HAND acima de 24,05", html)  # critério antigo, que deixava de fora os pontos mais altos

    def test_set2023_e_a_maior_cheia(self):
        cheias = {c["rotulo"]: c for c in self.d["meta"]["cheias_ref"]}
        self.assertNotIn("ref. mai/2024", cheias)
        self.assertEqual(cheias["mai/2024"]["regua_m"], 22.42)  # SGB; telemetria parou em 22,32 m
        hist = [c for c in cheias.values() if c.get("tipo") != "cota_oficial"]
        self.assertEqual(max(hist, key=lambda c: c["regua_m"])["rotulo"], "set/2023")
        self.assertEqual(self.alt["meta"]["cheia"]["regua_m"], cheias["set/2023"]["regua_m"])

    def test_ginasio_fica_dentro_da_agua_de_2023(self):
        gin = self.d["abrigos"][0]
        self.assertLessEqual(gin["cota_alaga_m"], self.alt["meta"]["cheia"]["hand_m"])

    def test_candidatos_antigos_saem_e_mancha_de_2023(self):
        self.assertEqual(self.d["candidatos"], [])
        self.assertIsNone(self.d["rota_cand"])
        m = self.alt["mancha_cheia"]
        self.assertAlmostEqual(m["nivel_hand_m"], 22.1, places=6)
        self.assertTrue(m["poligonos"])
        self.assertEqual(len(self.alt["cel_alta"]), len(self.d["cells"]))
        self.assertTrue(all(not c["casas"] for c, f in zip(self.d["cells"], self.alt["cel_alta"]) if f))
        self.assertNotIn("altos", DADOS["mucum"])


class TemplateTest(unittest.TestCase):
    """Partes do JS do painel e do HTML publicado que nenhum outro teste exercita."""

    def test_json_embutido_nao_fecha_o_script(self):
        # nome do OSM com "</script>" fecharia o script e o resto viraria HTML
        for c, html in HTML.items():
            with self.subTest(cidade=c):
                self.assertNotIn("</", payload_bruto(html))

    def test_folha_do_celular_vence_o_css_dos_logos(self):
        # assets/css/institutional_logos.css põe .hud a 84 px do topo com 100% da altura
        css = (RAIZ / "assets" / "css" / "institutional_logos.css").read_text(encoding="utf-8")
        self.assertIn("body[data-previne-map-signature] > :is(.hud, .card)", css)
        movel = TEMPLATE[TEMPLATE.index("@media (max-width:700px)"):]
        self.assertIn("body[data-previne-map-signature]>.hud.hud{margin-top:0;max-height:58vh", movel[:movel.index("}\n }")])

    def test_funcoes_puras_em_node(self):
        if not shutil.which("node"):
            self.skipTest("sem node")
        puras = TEMPLATE[TEMPLATE.index("// <puras>"):TEMPLATE.index("// </puras>")]
        teste = puras + r"""
const assert=require('assert');
const t=Date.parse('2026-10-24T22:45:00Z');
assert.strictEqual(horaLeitura({telemetria_ultima_em:'2026-10-24T19:45:00'}),t);   // sem fuso: -03:00
assert.strictEqual(horaLeitura({telemetria_ultima_em:'2026-10-24T19:45:00',telemetria_ultima_em_utc:'2026-10-24T22:45:00Z'}),t);
assert.strictEqual(idadeMin(t,t+30*6e4),30);
assert.ok(Number.isNaN(idadeMin(t,t-60*6e4)));   // leitura 1 h no futuro: fuso ou relógio errado
assert.ok(Number.isNaN(idadeMin(NaN,t)));
const zr=1.6;  // lim/cota em HAND, y e rio na régua
assert.strictEqual(situacaoSaida(18,20,17.5,null,zr),'nivel');
assert.strictEqual(situacaoSaida(18,20,17.5,17.6,zr),'agora');
assert.strictEqual(situacaoSaida(18,20,17.5,19.7,zr),'caminho_cortado');   // rio 19,7 >= 18+1,6
assert.strictEqual(situacaoSaida(18,17,17.5,18.7,zr),'casa_atingida');
assert.strictEqual(situacaoSaida(1,20,1.2,null,zr),'alerta');
console.log('ok');
"""
        with tempfile.TemporaryDirectory() as d:
            arq = os.path.join(d, "puras.js")
            with open(arq, "w", encoding="utf-8") as f:
                f.write(teste)
            r = subprocess.run(["node", arq], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ok", r.stdout)


class SimulacaoEvacuacaoTest(unittest.TestCase):
    """santa_tereza_painel_evacuacao.html (revisão de primeira visita, out/2026): o link que circula não
    pode mandar ninguém para o Ginásio sem aviso nem dar rota a partir de um toque longe das ruas."""

    @classmethod
    def setUpClass(cls):
        cls.html = (RAIZ / "santa_tereza_painel_evacuacao.html").read_text(encoding="utf-8")

    def test_leva_ao_painel_casa_a_casa(self):
        self.assertIn('class="casa-cta" href="santa_tereza_painel_casas.html#rotas"', self.html)
        self.assertIn("<title>Simulação da cheia", self.html)
        self.assertIn("setModo('rotas'); aj();", self.html)  # "Casas" sem classificação não abre primeiro

    def test_ginasio_avisa_que_alaga_no_mesmo_nivel_do_casa_a_casa(self):
        m = re.search(r"ABRIGO_ALAGA_HAND=\{santa_tereza_ginasio_esportes:([0-9.]+)\}", self.html)
        self.assertIsNotNone(m)
        gin = {a["id"]: a for a in DADOS["santa_tereza"]["abrigos"]}["santa_tereza_ginasio_esportes"]
        self.assertAlmostEqual(float(m.group(1)), gin["cota_alaga_m"], places=1)
        self.assertIn("não confirmado pela Defesa Civil", self.html)
        self.assertIn("já está embaixo d\\'água: não vá para lá", self.html)

    def test_toque_longe_da_rua_nao_vira_rota(self):
        self.assertIn("if(bd>LONGE_DA_RUA_M)", self.html)
        self.assertNotIn("você já está fora da área atingida", self.html)
        # a água não captura o toque nas casas
        self.assertIn("map.createPane('agua')", self.html)

    def test_celular_e_acessibilidade(self):
        h = self.html
        self.assertIn('<a href="tel:199"><b>199</b></a>', h)          # telefone que liga ao tocar
        self.assertIn('role="tablist"', h)
        self.assertIn("L.control.zoom({position:'topright'})", h)   # o painel cobria o + e o −
        self.assertIn("if(mexeuNoMapa&&!forcar)return;", h)          # trocar de aba não desfaz o zoom
        self.assertNotIn("{cache:'no-store'}", h)                    # dados revalidados, não baixados de novo
        self.assertIn('id="resumoToque"', h)                         # toque no celular não cobre o mapa
        self.assertNotIn(".mobile-sheet #sld{display:none}", h)       # folha aberta: o nível continua ajustável
        self.assertIn("setModo(bs[j].dataset.m);setSheetExpanded(true);", h)  # setas abrem a aba como o toque
        # a cópia de pesquisa é a mesma página, com caminhos ../
        pq = (RAIZ / "pesquisas" / "santa-tereza-painel-evacuacao.html").read_text(encoding="utf-8")
        self.assertIn('href="../santa_tereza_painel_casas.html#rotas"', pq)
        self.assertIn("if(bd>LONGE_DA_RUA_M)", pq)
        self.assertIn("const ARQ_ALTOS='../assets/data/rota_fuga/santa_tereza_rotas_altas_set2023.json'", pq)

    def test_rota_de_fuga_vai_ao_terreno_alto(self):
        # a rota do toque leva ao ponto alto (▲) pelo MDT, com os dados do casa a casa, não ao Ginásio
        h = self.html
        self.assertIn("const ARQ_ALTOS='assets/data/rota_fuga/santa_tereza_rotas_altas_set2023.json'", h)
        self.assertIn("r=rotaDe(s)", h)
        self.assertIn("if(novo||!rt.hidden)mostraResumo(res,!!cam)", h)  # resumo do celular acompanha o nível
        self.assertNotIn("saidaDaMancha", h)
        self.assertNotIn("até o Ginásio", h)
        dados = ler(RAIZ / "assets" / "data" / "rota_fuga" / "santa_tereza_rotas_altas_set2023.json")
        self.assertEqual(len(dados["z_nos"]), len(dados["nos"]))
        self.assertEqual(dados["margem_corte_m"], DADOS["santa_tereza"]["altos"]["meta"]["margem_corte_m"])
        self.assertTrue(all(isinstance(l["no"], int) and dados["no_alto"][l["no"]] for l in dados["locais"]))

    def test_rota_de_fuga_igual_ao_casa_a_casa_em_node(self):
        if not shutil.which("node"):
            self.skipTest("sem node")
        h = self.html
        puras = h[h.index("// <rotas-puras>"):h.index("// </rotas-puras>")]
        arq_json = RAIZ / "assets" / "data" / "rota_fuga" / "santa_tereza_rotas_altas_set2023.json"
        teste = "let RA=null;const vel=0.9,BANKFULL_M=1.6;let taxaCmH=90;\n" + puras + r"""
const assert=require('assert');
preparaRA(JSON.parse(require('fs').readFileSync(process.argv[2],'utf8')));
const out=RA.nos.map((_,i)=>{const r=rotaDe(i);return r?[Math.round(r.t),r.lim===Infinity?null:Math.round(r.lim*10)/10,RA.local[r.alvo]]:null;});
// ponto que vira ilha: a alternativa que não vira é mais longe, mas no máximo 15 min a mais
let k=RA.nos.findIndex((_,i)=>{const r=rotaDe(i);return r&&RA.local[r.alvo]>=0&&!RA.ligado[r.alvo]&&alternativa(i,r);});
assert.ok(k>=0);const r=rotaDe(k),a=alternativa(k,r);
assert.ok(RA.ligado[a.alvo]&&a.t>=r.t&&a.t<=r.t+900);
// saia antes: corte menos o erro do modelo e o que o rio sobe na caminhada (90 cm/h)
assert.strictEqual(regSair({lim:16,t:3600}),Math.floor((16-1.5-0.9+1.6)*10)/10);
// caminho cortado antes de o próprio ponto alagar: no nível do corte não há mais rota; 1,5 m antes já é tarde
const i=RA.nos.findIndex((_,j)=>{const q=rotaDe(j);return q&&q.lim>5&&q.lim<cotaV(j);}),q=rotaDe(i);
assert.ok(i>=0);
assert.strictEqual(classeFuga(i,q.lim,0.015),'rota_comprometida');
assert.strictEqual(classeFuga(i,q.lim-0.1,0.015),'critica');
assert.strictEqual(classeFuga(i,0,1e-6),'confortavel');
assert.strictEqual(classeFuga(RA.alto.indexOf(1),0,0.015),'alto');
console.log(JSON.stringify(out));
"""
        with tempfile.TemporaryDirectory() as d:
            arq = os.path.join(d, "rotas.js")
            with open(arq, "w", encoding="utf-8") as f:
                f.write(teste)
            r = subprocess.run(["node", arq, str(arq_json)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        js = json.loads(r.stdout)
        # margem_nos do casa a casa: [segundos, nível do corte] até o ponto alto mais perto pelo caminho que
        # fica seco por mais tempo; sem ponto alto ao alcance, a simulação ainda leva ao terreno alto mais perto
        terreno = 0
        for k, (a, b) in enumerate(zip(js, DADOS["santa_tereza"]["altos"]["margem_nos"])):
            if b is None and a is not None and a[2] < 0:
                terreno += 1
                continue
            if a is None or b is None:
                self.assertEqual(a, b, k)
                continue
            self.assertLessEqual(abs(a[0] - b[0]), 1, k)
            self.assertEqual(a[1], b[1], k)
        self.assertLess(terreno, len(js) // 10)

    def test_mai2024_nao_e_recorde(self):
        for nome in ("santa_tereza_inundacao.html", "santa_tereza_previsao_inundacao.html",
                     "santa_tereza_previsao_inundacao_usuario.html"):
            arq = RAIZ / nome
            if not arq.exists():
                continue
            s = arq.read_text(encoding="utf-8")
            with self.subTest(pagina=nome):
                self.assertNotIn("Recorde mai/2024", s)
                self.assertNotIn('"pico_obs_cm":2582', s)  # 25,82 m sem fonte primária; SGB: 22,42 m
                self.assertIn('"pico_obs_cm":2242', s)


class AbrigosGeojsonTest(unittest.TestCase):
    def setUp(self):
        self.feats = ler(ABRIGOS)["features"]

    def test_ginasio_continua_primeiro(self):
        # scripts/test_response_exercise.py lê features[0]
        self.assertEqual(self.feats[0]["properties"]["id"], "santa_tereza_ginasio_esportes")

    def test_mucum_igual_ao_painel(self):
        geo = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in self.feats
               if f["properties"]["municipio"] == "Muçum"}
        painel = {a["id"]: [a["lon"], a["lat"]] for a in DADOS["mucum"]["abrigos"]}
        self.assertEqual(set(geo), set(painel))
        for k, (lon, lat) in painel.items():
            with self.subTest(abrigo=k):
                self.assertAlmostEqual(geo[k][0], lon, places=5)
                self.assertAlmostEqual(geo[k][1], lat, places=5)

    def test_sem_campo_de_capacidade(self):
        # scripts/validate_santa_tereza_piloto.py barra "capacidade" no cadastro de abrigos
        self.assertFalse(any("capacidade" in f["properties"] for f in self.feats))


if __name__ == "__main__":
    unittest.main()
