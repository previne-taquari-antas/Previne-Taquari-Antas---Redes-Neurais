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

from test_santa_tereza_field_web import Scripts, function_code

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
                 "contratoContornosQuantitativos", "featureCenario", "projetarCasa", "carregarPontosCasas", "recalcularCotasCasas",
                 "indiceBordaNivel", "distanciaAteMancha", "classePorDistancia", "renderImpacto")
        functions = "\n".join(function_code(source, name) for name in names)
        if "function suspenderComparacaoCasas(" in source:
            functions += "\n" + function_code(source, "suspenderComparacaoCasas")
        code = r"""
const vm=require('node:vm');
const elements={},marker=()=>({setStyle(s){this.style=s;return this;},bindPopup(cb){this.popup=cb;return this;}});
const context={casas:[],estadoCasas:'carregando',estadoMancha:'carregando',rendererCasas:{},indiceAtual:null,contornosGeo:null,contornosOrdenados:[],
 BANKFULL_M:1.6,CAMADA_MAX:25,DIST_VERMELHO_M:30,DIST_LARANJA_M:100,TELA_M:160,
 LAT_M:110540,LON_M:111320*Math.cos(-29.17*Math.PI/180),
 CORES_CASAS:{atingida:'blue',iminente:'red',atencao:'orange',distante:'gray',indisponivel:'gray',referencia:'gray'},
 casasLayer:{clearLayers(){},addLayer(){}},BBcasas:{extend(){}},nivelAtual:()=>context.stage,
 document:{getElementById:id=>elements[id]||(elements[id]={innerHTML:'',textContent:''})},
 L:{circleMarker:marker}};
vm.createContext(context);vm.runInContext(FUNCTIONS,context);
const ring=[[-51.7402,-29.1802],[-51.7398,-29.1802],[-51.7398,-29.1798],[-51.7402,-29.1798],[-51.7402,-29.1802]];
const fc={metadata:{river_reference_method:'eixo_dominante_taquari_D8',
 source_id:'santa_tereza_lidar_campo_rio_principal_zero160_v1',cidade:'santa_tereza',hand_zero_cm:160,
 rio:'somente rio principal',superficie_inundacao:'CLIP_MOSAICO_LIDAR_RS.tif (LiDAR bruto)',
 superficie_roteamento:'FILL_CLIP_MOSAICO_LIDAR_RS.tif',backwater_hydrodynamic_calibration:true},features:[0,0.1,25].map(n=>({
 type:'Feature',properties:{nivel_m:n},geometry:{type:'Polygon',coordinates:[ring]}}))};
context.carregarPontosCasas({pontos:[[-29.18,-51.74],[-29.18,-51.741],[-29.18,-51.75]]});
const snapshot=()=>({classes:context.casas.map(x=>x.classe),distances:context.casas.map(x=>x.distancia),
 popups:context.casas.map(x=>x.marcador.popup()),panel:elements.painel?.innerHTML||''});
const cases={initial:snapshot()};
context.stage=1.65;context.renderImpacto();cases.loading=snapshot();
context.estadoMancha='validado';context.contornosGeo={...fc,metadata:{}};context.preparaContornos(fc);context.renderImpacto();cases.unsupported=snapshot();
context.contornosGeo=fc;context.recalcularCotasCasas();context.stage=1.65;context.renderImpacto();cases.valid=snapshot();
const selected=context.featureCenario(1.65)?.properties.nivel_m;
context.stage=26.61;context.renderImpacto();cases.above=snapshot();const above=context.featureCenario(26.61);
context.stage=1.6;context.renderImpacto();cases.reference=snapshot();
context.stage=1.65;context.renderImpacto();cases.restored=snapshot();
context.estadoMancha='previa';context.contornosGeo={...fc,metadata:{preview_only:true}};
context.renderImpacto();cases.preview=snapshot();const previewIndex=context.indiceBordaNivel(1.65);
context.estadoMancha='validado';context.contornosGeo=fc;context.renderImpacto();cases.afterPreview=snapshot();
context.estadoMancha='erro';context.renderImpacto();cases.error=snapshot();
context.contornosGeo=null;context.contornosOrdenados=[];context.renderImpacto();cases.failed=snapshot();
console.log(JSON.stringify({cases,selected,above,previewIndex,
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
                for key in ("initial", "loading", "unsupported", "failed", "above", "preview", "error"):
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
                self.assertIsNone(result["previewIndex"])

    def test_upper_decimetre_no_ceiling_clamp_and_valid_distance_results(self):
        for page in PAGES:
            with self.subTest(page=page):
                result = self.execute(page)
                self.assertEqual(result["selected"], 0.1)
                self.assertIsNone(result["above"])
                for key in ("valid", "restored", "afterPreview"):
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
                self.assertRegex(source, r"removeProperty\('--evac-sheet-height'\);\s*ajustarPopupAoPainel\(map\._popup\)")
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

    def test_actual_async_loader_rejects_incompatible_products_and_keeps_preview_visual_only(self):
        for page in PAGES:
            with self.subTest(page=page):
                source = (ROOT / page).read_text(encoding="utf-8")
                scripts = Scripts()
                scripts.feed(source)
                fetch_function = source[source.index("async function obterJson("):source.index("// Primeiro carrega os pontos pequenos.")]
                start = source.index("Promise.allSettled([")
                loader = source[start:source.index("</script>", start)]
                functions = fetch_function + "\n" + function_code(source, "contratoContornosQuantitativos")
                code = r"""
const vm=require('node:vm'),data=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
for(const block of data.scripts)new vm.Script(block); // syntax-check whole real inline scripts
const manifest={schema_version:'previne_painel_evacuacao_v1',status:'validado',validated:true,
 hydraulic_validation:true,river_reference_method_required:'eixo_dominante_taquari_D8'};
const meta={source_id:'santa_tereza_lidar_campo_rio_principal_zero160_v1',cidade:'santa_tereza',
 hand_zero_cm:160,rio:'somente rio principal',superficie_inundacao:'CLIP_MOSAICO_LIDAR_RS.tif (LiDAR bruto)',
 superficie_roteamento:'FILL_CLIP_MOSAICO_LIDAR_RS.tif',river_reference_method:'eixo_dominante_taquari_D8',
 backwater_hydrodynamic_calibration:true};
const previewMeta={status:'previa_visual_legada_nao_validada',preview_only:true,usable_for_building_risk:false,
 backwater_hydrodynamic_calibration:false,hand_zero_regua_m:1.6,hand_max_m:25};
const features=[{properties:{nivel_m:0}},{properties:{nivel_m:25}}];
async function run(name){
 const requests=[],ctx={BANKFULL_M:1.6,CAMADA_MAX:25,contornosGeo:null,contornosOrdenados:[],
  estadoMancha:'carregando',estadoCasas:'carregando',ultimaFeatureDesenhada:undefined,mode:name,
  pastaMancha:'data/',arquivoPontos:'points.json',modo:'impacto',BBcasas:{isValid:()=>true},
  console:{warn(){},error(){}},aj(){},solicitarRedraw(){},recalculaTerrenoAtual(){},
  recalcularCotasCasas(){ctx.houseCalls=(ctx.houseCalls||0)+1;},
  carregarPontosCasas(){ctx.estadoCasas='ok';},preparaContornos(fc){ctx.contornosOrdenados=fc.features;},
  setStatusMancha(status,msg){ctx.estadoMancha=status;ctx.msg=msg;},
  fetch:async url=>{requests.push(url);let payload;
   if(url.endsWith('points.json'))payload={pontos:[[-29.18,-51.74]]};
   else if(url.endsWith('manifesto_painel_evacuacao.json'))payload=name.startsWith('preview')?{...manifest,validated:false}:manifest;
   else if(url.endsWith('contornos_previa_visual_leve.json')){
    if(name==='previewMissing')return {ok:false,status:404,headers:{get:()=>0}};
    const m={...previewMeta};if(name==='previewRisk')m.usable_for_building_risk=true;
    if(name==='previewWrongDatum')m.hand_zero_regua_m=4;
    payload={metadata:m,features};
   }else{
    const m={...meta};if(name==='wrongDatum')m.hand_zero_cm=400;
    if(name==='wrongCity')m.cidade='mucum';if(name==='wrongSource')m.source_id='other';
    if(name==='wrongScope')m.rio='all rivers';if(name==='wrongSurface')m.superficie_inundacao='FILL';
    if(name==='pendingBackwater')m.backwater_hydrodynamic_calibration='not_validated';
    if(name==='mislabelledPreview')m.preview_only=true;
    payload={metadata:m,features};
   }
   return {ok:true,status:200,headers:{get:()=>0},json:async()=>payload};
  }};
 vm.createContext(ctx);vm.runInContext(data.functions,ctx);await vm.runInContext(data.loader,ctx);
 return {state:ctx.estadoMancha,houseCalls:ctx.houseCalls||0,contours:ctx.contornosOrdenados.length,requests};
}
(async()=>{const out={};for(const name of ['valid','previewValid','previewMissing','previewRisk','previewWrongDatum',
 'wrongDatum','wrongCity','wrongSource','wrongScope','wrongSurface','pendingBackwater','mislabelledPreview'])out[name]=await run(name);
 console.log(JSON.stringify(out));})().catch(e=>{console.error(e);process.exitCode=1;});
"""
                result = subprocess.run([shutil.which("node") or "node", "-e", code], cwd=ROOT,
                                        input=json.dumps({"scripts": scripts.blocks, "functions": functions, "loader": loader}),
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                cases = json.loads(result.stdout)
                self.assertEqual(cases["valid"]["state"], "validado")
                self.assertEqual(cases["valid"]["houseCalls"], 1)
                self.assertEqual(cases["previewValid"]["state"], "previa")
                self.assertEqual(cases["previewValid"]["houseCalls"], 0)
                for name in ("previewValid", "previewMissing", "previewRisk", "previewWrongDatum"):
                    self.assertNotIn("data/contornos_mancha_web.json", cases[name]["requests"])
                for name in ("previewMissing", "previewRisk", "previewWrongDatum"):
                    self.assertEqual(cases[name]["state"], "pendente")
                    self.assertEqual(cases[name]["contours"], 0)
                for name in ("wrongDatum", "wrongCity", "wrongSource", "wrongScope", "wrongSurface", "pendingBackwater", "mislabelledPreview"):
                    self.assertEqual(cases[name]["state"], "erro", name)
                    self.assertEqual(cases[name]["houseCalls"], 0, name)
                    self.assertEqual(cases[name]["contours"], 0, name)


if __name__ == "__main__":
    unittest.main()
