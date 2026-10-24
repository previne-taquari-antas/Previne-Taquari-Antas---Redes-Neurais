// Smoke real inline JS without Leaflet CDN or network.
// Exercises full startup and switching to both municipalities with DOM+Leaflet stubs.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('pesquisas/gt-risco-vida.html','utf8');
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert(scripts.length,'no inline scripts');
const code=scripts[scripts.length-1][1];
new vm.Script(code,{filename:'gt-risco-vida.inline.js'});
const els={};
function node(){return {style:{},textContent:'',innerHTML:'',children:[],addEventListener(){},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=[...items]}};}
function elem(id){return els[id]||(els[id]={...node(),
  value:id==='cidade'?'santa_tereza':id==='politica'?'exploratoria':id==='cota'?'13.4':undefined,
  checked:true,style:{},textContent:'',innerHTML:'',addEventListener(){}
});}
const geo={addTo(){return this},on(){return this},bindPopup(){return this},bindTooltip(){return this},getBounds(){return bounds}};
const bounds={extend(){return this},isValid(){return true},pad(){return this}};
const L={
  map(){return {setView(){return this},fitBounds(){return this},removeLayer(){return this}}},
  tileLayer(){return {...geo}},imageOverlay(){return {...geo}},layerGroup(){return {addTo(){return this},clearLayers(){}}},
  polyline(){return {...geo}},circleMarker(){return {...geo}},latLngBounds(){return {...bounds}}
};
const context={L,document:{getElementById:elem,createElement:()=>node(),createTextNode:text=>({textContent:String(text)})},console,Number,Math,Set,Map,Error,JSON,Array};
vm.runInNewContext(code,context,{timeout:20000,filename:'gt-risco-vida.inline.js'});
// Async mudaCidade triggers until its first await, all data inline so immediate.
assert(/Santa Tereza/.test(elem('resumo').innerHTML),'Santa Tereza not rendered');
assert(/565/.test(elem('resumo').innerHTML),'No 565 points in Santa Tereza summary');
elem('cidade').value='mucum';
vm.runInNewContext("mudaCidade()",context,{timeout:20000});
assert(/Muçum/.test(elem('resumo').innerHTML),'Muçum not rendered');
assert(/1937/.test(elem('resumo').innerHTML),'No 1937 points in Muçum summary');
assert(/Muçum/.test(elem('visaoResumo').textContent),'Floating map summary not rendered');
assert(/Clique/.test(elem('visaoDestino').textContent),'User must select a building before mapping a route');
vm.runInNewContext("exemploRota()",context,{timeout:20000});
assert(/Origem/.test(elem('visaoDestino').textContent),'Sample nearest high street route not displayed');
const mucRoute=vm.runInNewContext(`(()=>{const f=Object.fromEntries(d.meta.casas_campos.map((k,i)=>[k,i]));return d.casas.map(x=>rotaParaTerrenoAlto(d,x,f,13,0)).find(x=>x.rota)?.rota})()`,context,{timeout:20000});
assert(mucRoute&&mucRoute.metros>=60,'Muçum has no high-road path');
assert(mucRoute.cotaSaida>=15,'Muçum destination does not meet HAND +2 m criterion');

elem('cidade').value='santa_tereza';
vm.runInNewContext("mudaCidade()",context,{timeout:20000});
vm.runInNewContext("selecionada=388;rede(18.9,'exploratoria')",context,{timeout:20000});
assert(/já está na mancha simulada/.test(elem('visaoDestino').textContent),'Flooded origin should not suggest a route');
assert(elem('voltarCota').hidden===false,'Earlier high-road access scenario should be available for origin 388');
const stRoute=vm.runInNewContext(`(()=>{const f=Object.fromEntries(d.meta.casas_campos.map((k,i)=>[k,i]));return d.casas.map(x=>rotaParaTerrenoAlto(d,x,f,13.4,0)).find(x=>x.rota)?.rota})()`,context,{timeout:20000});
assert(stRoute&&stRoute.cotaSaida>=15.4,'Santa Tereza destination is not elevated enough');
assert(stRoute.arestas.every(idx=>{let e=({edges:vm.runInNewContext('d.edges',context)}) .edges[idx];return e[3]===0&&e[4]>13.4;}),'Route crosses flooded, unknown or bridge segments');
console.log('OK GT map: both cities, nearest high-street routing and flood origin tested');
