"""Actual panel callbacks: unavailable comparison must not imply distance/safety.

Node runs functions read from the HTML; only DOM/Leaflet are recorder stubs.
Optional STZ_EVAC_TEST_REF reads historical HTML via git show for counterproof.
No contour regeneration, observed inundation or route approval.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from test_santa_tereza_field_web import function_code

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("santa_tereza_painel_evacuacao.html", "pesquisas/santa-tereza-painel-evacuacao.html")


class EvacuationUnknownTests(unittest.TestCase):
    def execute(self, page):
        if os.environ.get("STZ_EVAC_TEST_REF"):
            source = subprocess.run(["git", "show", os.environ["STZ_EVAC_TEST_REF"] + ":" + page],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
        else:
            source = (ROOT / page).read_text(encoding="utf-8")
        names = ("pontoNoAnel", "pontoNaGeom", "bboxGeom", "preparaContornos", "itemContem",
                 "featureCenario", "projetarCasa", "carregarPontosCasas", "recalcularCotasCasas",
                 "indiceBordaNivel", "distanciaAteMancha", "classePorDistancia", "renderImpacto")
        functions = "\n".join(function_code(source, name) for name in names)
        if "function suspenderComparacaoCasas(" in source:
            functions += "\n" + function_code(source, "suspenderComparacaoCasas")
        code = r"""
const vm=require('node:vm');
const elements={},marker=()=>({setStyle(s){this.style=s;return this;},bindPopup(cb){this.popup=cb;return this;}});
const context={casas:[],estadoCasas:'carregando',indiceAtual:null,contornosGeo:null,contornosOrdenados:[],
 BANKFULL_M:1.6,CAMADA_MAX:25,DIST_VERMELHO_M:30,DIST_LARANJA_M:100,TELA_M:160,
 LAT_M:110540,LON_M:111320*Math.cos(-29.17*Math.PI/180),
 CORES_CASAS:{atingida:'blue',iminente:'red',atencao:'orange',distante:'gray',indisponivel:'gray',referencia:'gray'},
 casasLayer:{clearLayers(){},addLayer(){}},BBcasas:{extend(){}},nivelAtual:()=>context.stage,
 document:{getElementById:id=>elements[id]||(elements[id]={innerHTML:'',textContent:''})},
 L:{circleMarker:marker}};
vm.createContext(context);vm.runInContext(FUNCTIONS,context);
const ring=[[-51.7402,-29.1802],[-51.7398,-29.1802],[-51.7398,-29.1798],[-51.7402,-29.1798],[-51.7402,-29.1802]];
const fc={metadata:{river_reference_method:'eixo_dominante_taquari_D8'},features:[0,0.1,25].map(n=>({
 type:'Feature',properties:{nivel_m:n},geometry:{type:'Polygon',coordinates:[ring]}}))};
context.carregarPontosCasas({pontos:[[-29.18,-51.74],[-29.18,-51.741],[-29.18,-51.75]]});
const snapshot=()=>({classes:context.casas.map(x=>x.classe),distances:context.casas.map(x=>x.distancia),
 popups:context.casas.map(x=>x.marcador.popup()),panel:elements.painel?.innerHTML||''});
const cases={initial:snapshot()};
context.stage=1.65;context.renderImpacto();cases.loading=snapshot();
context.contornosGeo={...fc,metadata:{}};context.preparaContornos(fc);context.renderImpacto();cases.unsupported=snapshot();
context.contornosGeo=fc;context.recalcularCotasCasas();context.stage=1.65;context.renderImpacto();cases.valid=snapshot();
const selected=context.featureCenario(1.65)?.properties.nivel_m;
context.stage=26.61;context.renderImpacto();cases.above=snapshot();const above=context.featureCenario(26.61);
context.stage=1.6;context.renderImpacto();cases.reference=snapshot();
context.stage=1.65;context.renderImpacto();cases.restored=snapshot();
context.contornosGeo=null;context.contornosOrdenados=[];context.renderImpacto();cases.failed=snapshot();
console.log(JSON.stringify({cases,selected,above,
 invalidDistance:context.classePorDistancia(null),noIndex:context.distanciaAteMancha(context.casas[0],null)}));
""".replace("FUNCTIONS", json.dumps(functions))
        result = subprocess.run([shutil.which("node") or "node", "-e", code], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_unavailable_loading_failure_and_suspended_popups_do_not_claim_outside(self):
        for page in PAGES:
            with self.subTest(page=page):
                result = self.execute(page)
                for key in ("initial", "loading", "unsupported", "failed", "above"):
                    case = result["cases"][key]
                    self.assertEqual(case["classes"], ["indisponivel"] * 3)
                    self.assertEqual(case["distances"], [None] * 3)
                    for popup in case["popups"]:
                        self.assertIn("indisponível ou suspensa", popup)
                        self.assertNotIn("Fora da faixa", popup)
                        self.assertNotIn("Primeira interseção", popup)
                        self.assertIn("não significa segurança", popup)
                        self.assertIn("Não é alerta oficial", popup)
                self.assertEqual(result["invalidDistance"], "indisponivel")
                self.assertIsNone(result["noIndex"])

    def test_upper_decimetre_no_ceiling_clamp_and_valid_distance_results(self):
        for page in PAGES:
            with self.subTest(page=page):
                result = self.execute(page)
                self.assertEqual(result["selected"], 0.1)
                self.assertIsNone(result["above"])
                for key in ("valid", "restored"):
                    case = result["cases"][key]
                    self.assertEqual(case["classes"], ["atingida", "atencao", "distante"])
                    self.assertIn("Fora da faixa de proximidade de 100 m", case["popups"][2])
                    self.assertIn("Primeira interseção", case["popups"][0])
                self.assertEqual(result["cases"]["reference"]["classes"], ["referencia"] * 3)
                for popup in result["cases"]["reference"]["popups"]:
                    self.assertIn("comparação de proximidade não realizada", popup)
                    self.assertNotIn("Fora da faixa", popup)

    def test_popup_padding_accounts_for_open_sheet_and_does_not_loop_updates(self):
        for page in PAGES:
            with self.subTest(page=page):
                source = (ROOT / page).read_text(encoding="utf-8")
                function = function_code(source, "ajustarPopupAoPainel")
                self.assertIn("map.on('popupopen',event=>ajustarPopupAoPainel(event.popup))", source)
                self.assertIn("ajustarPopupAoPainel(map._popup)", source)
                code = r"""
const vm=require('node:vm');let mobile=true,updates=0;
const popup={options:{},update(){updates++;}},ctx={
 window:{matchMedia:()=>({matches:mobile})},
 document:{querySelector:()=>({getBoundingClientRect:()=>({top:495})})},
 map:{getContainer:()=>({getBoundingClientRect:()=>({bottom:1000})})}};
vm.createContext(ctx);vm.runInContext(FUNCTION,ctx);
ctx.ajustarPopupAoPainel(popup);const first=JSON.stringify(popup.options);
ctx.ajustarPopupAoPainel(popup);const sameUpdates=updates;
mobile=false;ctx.ajustarPopupAoPainel(popup);
console.log(JSON.stringify({first:JSON.parse(first),sameUpdates,desktop:popup.options,updates}));
""".replace("FUNCTION", json.dumps(function))
                result = subprocess.run([shutil.which("node") or "node", "-e", code], cwd=ROOT,
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data["first"]["autoPanPaddingBottomRight"], [12, 541])
                self.assertEqual(data["sameUpdates"], 1)
                self.assertEqual(data["desktop"]["autoPanPaddingBottomRight"], [12, 12])
                self.assertEqual(data["updates"], 2)


if __name__ == "__main__":
    unittest.main()
