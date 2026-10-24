// Smoke real inline JS without Leaflet CDN or network.
// Exercises full startup and switching to both municipalities with DOM+Leaflet stubs.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('pesquisas/gt-risco-vida.html','utf8');
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert(scripts.length,'no inline scripts');
const code=scripts[scripts.length-1][1];
new vm.Script(code,{filename:'gt-risco-vida.inline.js'});
const els={};
function elem(id){return els[id]||(els[id]={
  value:id==='cidade'?'santa_tereza':id==='politica'?'exploratoria':id==='cota'?'13.4':undefined,
  checked:true,style:{},textContent:'',innerHTML:'',addEventListener(){}
});}
const geo={addTo(){return this},on(){return this},bindPopup(){return this}};
const bounds={extend(){return this},isValid(){return true},pad(){return this}};
const L={
  map(){return {setView(){return this},fitBounds(){return this},removeLayer(){return this}}},
  tileLayer(){return {...geo}},imageOverlay(){return {...geo}},layerGroup(){return {addTo(){return this},clearLayers(){}}},
  polyline(){return {...geo}},circleMarker(){return {...geo}},latLngBounds(){return {...bounds}}
};
const context={L,document:{getElementById:elem},console,Number,Math,Set,Map,Error,JSON,Array};
vm.runInNewContext(code,context,{timeout:20000,filename:'gt-risco-vida.inline.js'});
// Async mudaCidade triggers until its first await, all data inline so immediate.
assert(/Santa Tereza/.test(elem('resumo').innerHTML),'Santa Tereza not rendered');
assert(/565/.test(elem('resumo').innerHTML),'No 565 points in Santa Tereza summary');
elem('cidade').value='mucum';
vm.runInNewContext("mudaCidade()",context,{timeout:20000});
assert(/Muçum/.test(elem('resumo').innerHTML),'Muçum not rendered');
assert(/1937/.test(elem('resumo').innerHTML),'No 1937 points in Muçum summary');
console.log('OK GT map renders both cities + points without network fetch');
