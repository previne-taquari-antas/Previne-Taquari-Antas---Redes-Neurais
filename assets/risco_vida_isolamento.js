/* PREVINE — pesquisa sobre perda de acessibilidade. Não é roteamento de emergência. */
"use strict";
const analisarIsolamento = function analisarIsolamento(D, cfg={}) {
  const F=Object.fromEntries(D.meta.casas_campos.map((x,i)=>[x,i]));
  const N=D.nos.length, edges=D.edges, home=D.casas, includeCandidates=!!cfg.candidatos;
  const levels=[...new Set([...Array.from({length:26},(_,i)=>i),Number(D.meta.nivel_projeto_m)])].sort((a,b)=>a-b);
  const theta=(D.meta.bankfull_m==null?null:Number(D.meta.bankfull_m));
  const R=6371000,rad=Math.PI/180,cy=Math.cos((D.nos.reduce((s,p)=>s+p[0],0)/N)*rad);
  const meterX=111320*cy,meterY=110540;
  const coordinates=D.nos.map(p=>[p[1]*meterX,p[0]*meterY]);
  function segDist(px,py,a,b){
    const ax=coordinates[a][0],ay=coordinates[a][1],bx=coordinates[b][0],by=coordinates[b][1];
    const ux=bx-ax,uy=by-ay,len2=ux*ux+uy*uy;
    const t=len2?Math.max(0,Math.min(1,((px-ax)*ux+(py-ay)*uy)/len2)):0;
    return {dist:Math.hypot(px-(ax+t*ux),py-(ay+t*uy)),frac:t};
  }
  // Use the projected road connection already recorded by the original model.
  // It is an approximation, not a verification of each property's access.
  const links=home.map(c=>{
    if(c[F.proj_lon]==null||c[F.proj_lat]==null)return [];
    const px=c[F.proj_lon]*meterX,py=c[F.proj_lat]*meterY;
    let best=Infinity,candidates=[];
    for(let j=0;j<edges.length;j++){
      const e=edges[j],seg=segDist(px,py,e[0],e[1]);
      if(seg.dist<best){best=seg.dist;}
      if(seg.dist<=8)candidates.push({j,dist:seg.dist,frac:seg.frac});
    }
    if(best>8)return [];
    return candidates.filter(x=>x.dist<=best+1).sort((a,b)=>a.dist-b.dist).slice(0,4);
  });
  const allShelters=D.abrigos.map(s=>({...s,tipo:"abrigo_cadastrado"}));
  const allCands=(D.candidatos||[]).map(s=>({...s,tipo:"candidato_nao_validado"}));
  const sources=includeCandidates?allShelters.concat(allCands):allShelters;
  function graph(level,conditional){
    const dryNode=D.cota_no.map(z=>z==null?conditional:Number(z)>level+1e-8);
    const usable=edges.map(([a,b,_fraction,_foot,threshold])=>dryNode[a]&&dryNode[b]&&(threshold==null?conditional:Number(threshold)>level+1e-8));
    const adj=Array.from({length:N},()=>[]);
    edges.forEach(([a,b],j)=>{if(usable[j]){const dist=Math.hypot(coordinates[a][0]-coordinates[b][0],coordinates[a][1]-coordinates[b][1]);adj[a].push([b,dist]);adj[b].push([a,dist]);}});
    const dist=Array(N).fill(Infinity), dest=Array(N).fill(null), heap=[];
    const push=(d,n,id)=>{let k=heap.length;heap.push([d,n,id]);while(k>0){let p=(k-1)>>1;if(heap[p][0]<=d)break;heap[k]=heap[p];k=p;}heap[k]=[d,n,id];};
    const pop=()=>{if(!heap.length)return null;const ans=heap[0],end=heap.pop();if(heap.length){let k=0;while(true){const l=2*k+1,r=l+1;if(l>=heap.length)break;const child=r<heap.length&&heap[r][0]<heap[l][0]?r:l;if(heap[child][0]>=end[0])break;heap[k]=heap[child];k=child;}heap[k]=end;}return ans;};
    let nsources=0;
    for(const s of sources){const n=s.node, z=s.cota_alaga_m;
      if(!Number.isInteger(n)||n<0||n>=N||!dryNode[n]||!(z==null?conditional:Number(z)>level+1e-8))continue;
      if(dist[n]===0)continue;dist[n]=0;dest[n]=s.id;push(0,n,s.id);nsources++;
    }
    while(heap.length){
      const it=pop(),[dd,node,id]=it;if(dd>dist[node]+1e-8)continue;
      for(const [next,w] of adj[node]){const dnew=dd+w;
        if(dnew+1e-8<dist[next]){dist[next]=dnew;dest[next]=id;push(dnew,next,id);}
      }
    }
    const assignments=home.map((c,i)=>{
      let best=Infinity,choice=null;
      for(const l of links[i]){if(!usable[l.j])continue;
        const [a,b]=edges[l.j];
        const len=Math.hypot(coordinates[a][0]-coordinates[b][0],coordinates[a][1]-coordinates[b][1]);
        const toA=l.frac*len+dist[a],toB=(1-l.frac)*len+dist[b];
        if(toA<best){best=toA;choice=dest[a];}
        if(toB<best){best=toB;choice=dest[b];}
      }
      return Number.isFinite(best)?{destino:choice,distancia_via_m:Math.round(best),alcancavel:true}:{destino:null,distancia_via_m:null,alcancavel:false};
    });
    return {assignments,n_sources:nsources,known_edges:usable.filter(Boolean).length};
  }
  const scenarios=levels.map(level=>({level,cond:graph(level,true),estrito:graph(level,false)}));
  const cur=scenarios.find(x=>x.level===Number(D.meta.nivel_projeto_m));
  const at0=scenarios[0],bycase=[];
  const sums={n_edificacoes_proxy:home.length,casas_na_mancha_modelo:0,casas_secas_ligadas_estrito:0,casas_secas_ligadas_condicional:0,casas_secas_so_condicional:0,casas_secas_sem_destino_no_grafo:0,casas_secas_sem_conexao_via:0,casas_com_cota_desconhecida:0,casas_secas_perderam_destino_desde_nivel_zero:0};
  home.forEach((c,i)=>{
    const cota=c[F.cota_alaga],unknown=cota==null,wet=!unknown&&cota<=cur.level,linksN=links[i].length;
    const e=cur.estrito.assignments[i],o=cur.cond.assignments[i];
    const initial=at0.cond.assignments[i].alcancavel;
    let classe;
    if(wet){classe="ATINGIDA_PELO_CENARIO";sums.casas_na_mancha_modelo++;}
    else if(unknown){classe="COTA_DA_EDIFICACAO_INDETERMINADA";sums.casas_com_cota_desconhecida++;}
    else if(!linksN){classe="SEM_CONEXAO_VIARIA_RECONSTRUIDA";sums.casas_secas_sem_conexao_via++;}
    else if(e.alcancavel){classe="CONEXAO_MODELADA_SEM_TRECHOS_BLOQUEADOS";sums.casas_secas_ligadas_estrito++;sums.casas_secas_ligadas_condicional++;}
    else if(o.alcancavel){classe="CONEXAO_DEPENDE_DE_DADOS_INDETERMINADOS";sums.casas_secas_so_condicional++;sums.casas_secas_ligadas_condicional++;}
    else{classe="SEM_DESTINO_ACESSIVEL_NO_GRAFO";sums.casas_secas_sem_destino_no_grafo++;}
    if(!wet&&!unknown&&initial&&!o.alcancavel)sums.casas_secas_perderam_destino_desde_nivel_zero++;
    let perdeu=null,anterior=null;
    if(initial){for(const s of scenarios){
      if(!s.cond.assignments[i].alcancavel){
        perdeu={hand_limite_superior_m:s.level,hand_limite_inferior_m:anterior,regua_limite_superior_m:theta==null?null:Math.round((theta+s.level)*100)/100,antes_de_inundar:cota!=null&&s.level<cota};
        break;
      }
      anterior=s.level;
    }}
    bycase.push({lat:c[F.lat],lon:c[F.lon],classe,cota_alaga_hand_m:cota,primeira_perda_acesso:perdeu,acesso_estrito:e.alcancavel,acesso_condicional:o.alcancavel,destino_modelado:o.destino,distancia_via_aproximada_m:o.distancia_via_m,ponto_conexao_via:linksN?true:false,domicilio_confirmado:false});
  });
  const bylevel=scenarios.map(s=>{
    let seca=0,atingida=0,cond=0,estrito=0,perda=0,desconhecida=0;
    for(let i=0;i<home.length;i++){
      const cota=home[i][F.cota_alaga];if(cota==null){desconhecida++;continue;}
      if(cota<=s.level){atingida++;continue;}
      seca++;
      if(s.cond.assignments[i].alcancavel)cond++;
      if(s.estrito.assignments[i].alcancavel)estrito++;
      if(at0.cond.assignments[i].alcancavel&&!s.cond.assignments[i].alcancavel)perda++;
    }
    return {hand_m:s.level,regua_m:theta==null?null:Math.round((theta+s.level)*100)/100,edificacoes_secas:seca,edificacoes_atingidas:atingida,cota_desconhecida:desconhecida,conectadas_condicional:cond,conectadas_estrito:estrito,perderam_acesso_condicional:perda,fontes_condicional:s.cond.n_sources,fontes_estrito:s.estrito.n_sources};
  });
  return {meta:{municipio:D.meta.municipio,origem:"painel_casas_publicado",origem_gerado_em:D.meta.gerado_em,cenario_regua_m:theta==null?null:cur.level+theta,cenario_hand_m:cur.level,candidatos_incluidos:includeCandidates,regra:"bloqueio de trechos com cota_min <= nivel e nós afetados; duas hipóteses para cota ausente",hipoteses:{estrito:"cota nula fecha trecho/nó/destino",condicional:"cota nula é tratada como transitável apenas na hipótese exploratória"},limitacoes:["identificação domiciliar só por OSM","acesso casa-rua deduzido de geometria projetada, não vistoriado","cota nula pode ser área acima de HAND25 ou fora do raster; distinção não disponível","ponte sem certificação estrutural","níveis e datum carecem validação independente","não é orientação de evacuação"]},summary:sums,series:bylevel,casas:bycase};
};
const decodePanel = function decodePanel(t){const marker="const D=";const i=t.indexOf(marker);if(i<0)throw Error("painel sem const D");const start=i+marker.length;let level=0,inString=false,escaped=false;for(let j=start;j<t.length;j++){const c=t[j];if(inString){if(escaped)escaped=false;else if(c==="\\")escaped=true;else if(c==='"')inString=false;continue;}if(c==='"'){inString=true;continue;}if(c==="{")level++;else if(c==="}"){level--;if(level===0)return JSON.parse(t.slice(start,j+1));}}throw Error("JSON do painel não terminado");};
if(typeof module !== "undefined" && module.exports) module.exports = {analisarIsolamento,decodePanel};
if(typeof window !== "undefined") window.PreVineIsolamento = {analisarIsolamento,decodePanel};
