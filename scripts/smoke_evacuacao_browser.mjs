import { chromium } from 'playwright';

const BASE = 'https://previne-taquari-antas.github.io/Previne-Taquari-Antas---Redes-Neurais/';
const paths = ['santa_tereza_painel_evacuacao.html', 'pesquisas/santa-tereza-painel-evacuacao.html'];
const browser = await chromium.launch({ headless: true });
let failures = 0;
try {
 for (const path of paths) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('response', res => {if(/contornos_previa_visual_leve|manifesto_painel_evacuacao/.test(res.url())) console.log('ASSET',res.status(),res.url());});
  const url=BASE+path+'?smoke='+Date.now();
  console.log('ABRINDO',url);
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:90000});
  console.log('HTTP',response?.status());
  await page.waitForFunction(()=>typeof estadoMancha!=='undefined'&&['previa','validado','erro','pendente'].includes(estadoMancha),{timeout:45000});
  await page.waitForTimeout(2500);
  const state = await page.evaluate(()=>({
    estado: estadoMancha,
    pontos: casas.length,
    contornos: contornosOrdenados.length,
    msg: document.getElementById('sheetState')?.textContent,
    playDisabled:document.getElementById('quickPlay')?.disabled
  }));
  console.log('ESTADO',path,JSON.stringify(state),'JS_ERRORS',JSON.stringify(errs));
  if(response?.status()!==200||state.estado!=='previa'||state.playDisabled||state.contornos<5||errs.length){
    failures++;await page.screenshot({path:'smoke_'+(path.startsWith('pesquisas')?'pesquisa':'publico')+'.png',fullPage:true});
    await page.close();continue;
  }
  await page.locator('#quickPlay').click({force:true});
  await page.waitForTimeout(600);
  const played = await page.evaluate(()=>({
    nivel:Number(document.getElementById('sld').value),
    frames:manchaLayer.getLayers().length,
    running:animTimer!==null,
    drawn:ultimaFeatureDesenhada!==null&&ultimaFeatureDesenhada!==undefined
  }));
  console.log('ANIMADO',path,JSON.stringify(played));
  if(played.frames<1||!played.drawn||played.nivel<=1.6){failures++;}
  await page.screenshot({path:'smoke_'+(path.startsWith('pesquisas')?'pesquisa':'publico')+'.png',fullPage:true});
  await page.close();
 }
} finally {await browser.close();}
if(failures){console.error('FALHAS',failures);process.exit(1);}
console.log('OK - ambas as paginas desenham a mancha azul da previa');
