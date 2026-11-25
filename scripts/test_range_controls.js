const assert=require('node:assert/strict');
let jobs=new Map(),id=0;
global.requestAnimationFrame=fn=>{jobs.set(++id,fn);return id;};global.cancelAnimationFrame=id=>jobs.delete(id);
const {bindRange}=require('../assets/js/site_runtime');
let state=0,draws=0;const input={value:'0',setAttribute(k,v){this[k]=v;}};
bindRange(input,value=>state=value,()=>draws++,value=>value+' m');
for(let i=1;i<=100;i++){input.value=String(i);input.oninput();}
assert.equal(state,100);assert.equal(draws,0);assert.equal(jobs.size,1);assert.equal(input['aria-valuetext'],'100 m');
input.onchange();assert.equal(draws,1);assert.equal(jobs.size,0);
console.log('OK shared ranges: 100 input events, final value retained, one render, accessible value updated');
