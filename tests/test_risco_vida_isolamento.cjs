#!/usr/bin/env node
/* Regressões mínimas do estudo de isolamento. Execute: node tests/test_risco_vida_isolamento.cjs */
"use strict";
const assert=require("node:assert/strict");
const {analisarIsolamento,decodePanel}=require("../assets/risco_vida_isolamento.js");
const fields=["lat","lon","proj_lat","proj_lon","no","abrigo","dist_m","agua_m","na_mancha","tempo_s","subida_m","excede","tempo_direto_s","agua_direto_m","cota_alaga","situacao","cand","tempo_cand_s","no_cand","pessoas"];
function fixture({cenario=4,limiar=5,incerto=false,abrigo=20}={}){
  const c=Array(fields.length).fill(null);
  Object.assign(c,{0:0,1:0.0002,2:0,3:0.0002,14:19});
  return {meta:{municipio:"Teste",gerado_em:"synthetic",casas_campos:fields,bankfull_m:1.6,nivel_projeto_m:cenario},
    nos:[[0,0],[0,0.001],[0,0.002]],cota_no:[20,20,20],
    edges:[[0,1,0,0,20],[1,2,0,0,incerto?null:limiar]],casas:[c],
    abrigos:[{id:"abrigo_A",node:2,cota_alaga_m:abrigo}],
    candidatos:[{id:"local_alto_sem_vistoria",node:0,cota_alaga_m:20}]};
}
const before=analisarIsolamento(fixture({cenario:4}));
assert.equal(before.summary.casas_secas_ligadas_estrito,1);
assert.equal(before.casas[0].acesso_estrito,true);
const after=analisarIsolamento(fixture({cenario:6}));
assert.equal(after.summary.casas_secas_sem_destino_no_grafo,1);
assert.equal(after.casas[0].primeira_perda_acesso.hand_limite_superior_m,5);
assert.equal(after.casas[0].primeira_perda_acesso.antes_de_inundar,true);
assert.equal(after.casas[0].acesso_condicional,false);
const candidate=analisarIsolamento(fixture({cenario:6}),{candidatos:true});
assert.equal(candidate.casas[0].acesso_estrito,true);
assert.equal(candidate.casas[0].destino_modelado,"local_alto_sem_vistoria");
const unknownEdge=analisarIsolamento(fixture({cenario:4,incerto:true}));
assert.equal(unknownEdge.casas[0].acesso_estrito,false);
assert.equal(unknownEdge.casas[0].acesso_condicional,true);
const unknownShelter=analisarIsolamento(fixture({cenario:4,abrigo:null}));
assert.equal(unknownShelter.casas[0].acesso_estrito,false);
assert.equal(unknownShelter.casas[0].acesso_condicional,true);
const floodedHome=fixture({cenario:20});
assert.equal(analisarIsolamento(floodedHome).summary.casas_na_mancha_modelo,1);
const unknownHome=fixture({cenario:7});unknownHome.casas[0][14]=null;
const r=analisarIsolamento(unknownHome);
assert.equal(r.summary.casas_com_cota_desconhecida,1);
assert.equal(r.summary.casas_secas_perderam_destino_desde_nivel_zero,0);
const decoded=decodePanel('<script>const D={"meta":{"x":"teste"},"num":3}, M=D.meta;</script>');
assert.equal(decoded.num,3);
assert.equal(decoded.meta.x,'teste');
console.log("PASS: bloqueio de rua; início do isolamento; candidatos; cota ausente; casa inundada; parser.");
