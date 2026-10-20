(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  root.PrevineSiteRuntime=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  // The timer covers the body too: headers alone do not complete a request.
  async function fetchResource(url,options){
    const settings=Object.assign({},options);
    const timeoutMs=settings.timeoutMs||12000;
    delete settings.timeoutMs;
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeoutMs);
    try {
      const response=await fetch(url,Object.assign(settings,{signal:controller.signal}));
      const body=await response.text();
      return {ok:response.ok,status:response.status,json:async()=>JSON.parse(body),text:async()=>body};
    } finally { clearTimeout(timer); }
  }
  function imageTask(executor,timeoutMs){
    return new Promise(resolve=>{
      const timer=setTimeout(resolve,timeoutMs||12000);
      const finish=()=>{clearTimeout(timer);resolve();};
      try { executor(finish); } catch(error) { finish(); }
    });
  }
  function installTileFallback(map,primary,fallback){
    let errors=[];
    const onError=()=>{
      if(!map.hasLayer(primary)) return;
      const now=Date.now();
      errors=errors.filter(time=>now-time<15000);errors.push(now);
      if(errors.length<3) return;
      if(!map.hasLayer(fallback)) fallback.addTo(map);
      map.removeLayer(primary);
      errors=[];
    };
    primary.on('tileerror',onError);
    map.on('unload',()=>primary.off('tileerror',onError));
  }
  return {fetchResource,imageTask,installTileFallback};
});
