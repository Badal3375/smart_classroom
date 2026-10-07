(function(){
const cfg=window.LIVE_CFG;const $=id=>document.getElementById(id);
const video=$('video'),overlay=$('overlay'),log=$('resultLog'),feed=$('feedList');
let stream=null,timer=null,busy=false;
const COL={matched:'#10b981',unknown:'#f59e0b',spoof:'#ef4444',low_quality:'#94a3b8',needs_iris:'#06b6d4'};
function renderFeed(f){
  $('cPresent').textContent=f.present;$('cLate').textContent=f.late;$('cAbsent').textContent=f.absent;$('cTotal').textContent=f.total;
  const pct=f.total?Math.round(100*f.marked/f.total):0;$('bar').style.width=pct+'%';$('barTxt').textContent=f.marked+' / '+f.total+' recognised';
  feed.innerHTML=f.recent.map(r=>`<div class="feed-item ${r.code} bg-white border rounded p-2 mb-2 d-flex justify-content-between"><div><strong>${r.name}</strong><div class="small text-muted">${r.roll} · ${r.method} · ${r.time}</div></div><div class="text-end"><span class="badge text-bg-${r.code=='L'?'warning':'success'}">${r.status}</span><div class="small text-muted">${r.confidence}%</div></div></div>`).join('')||'<div class="text-muted small">Waiting for recognitions...</div>';
}
function renderResults(res,scale){
  const ctx=overlay.getContext('2d');overlay.width=video.clientWidth||640;overlay.height=video.clientHeight||480;ctx.clearRect(0,0,overlay.width,overlay.height);
  res.forEach(r=>{
    if(scale&&r.box){const [x,y,w,h]=r.box.map(v=>v*scale);ctx.strokeStyle=COL[r.status]||'#fff';ctx.lineWidth=3;ctx.strokeRect(x,y,w,h);ctx.fillStyle=COL[r.status]||'#fff';ctx.font='14px sans-serif';ctx.fillText((r.student||r.status)+' '+(r.confidence?Math.round(r.confidence*100)+'%':''),x,Math.max(14,y-5));}
    const d=document.createElement('div');d.className='border rounded p-2 mb-1 small';d.style.borderLeft='4px solid '+(COL[r.status]||'#ccc');
    d.innerHTML=`<strong>${r.student||(r.status=='spoof'?'Spoof attempt':'Unknown person')}</strong> <span class="badge" style="background:${COL[r.status]||'#999'}">${r.status}</span>${r.expected?` <span class="text-muted">[test: ${r.expected}]</span>`:''}<br>face ${r.face_score}${r.iris_score!=null?' · iris '+r.iris_score:''}${r.liveness!=null?' · liveness '+r.liveness:''}${r.method?' · '+r.method:''}<br><span class="text-muted">${r.message||''}</span>`;
    log.prepend(d);while(log.children.length>25)log.lastChild.remove();
  });
}
async function sendFrame(){
  if(busy||!stream&&!video.src)return;busy=true;
  try{const g=grab(video);const out=await postJSON(cfg.frameUrl,{image:g.url});if(out.ok){renderResults(out.results,video.clientWidth/g.w);renderFeed(out.feed);}}catch(e){console.error(e)}busy=false;
}
$('btnCam')?.addEventListener('click',async()=>{stream=await startCamera(video);if(stream){clearInterval(timer);timer=setInterval(sendFrame,2000);$('btnCam').disabled=true;}});
$('videoFile')?.addEventListener('change',e=>{const f=e.target.files[0];if(!f)return;if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}video.srcObject=null;video.src=URL.createObjectURL(f);video.loop=true;video.play();clearInterval(timer);timer=setInterval(sendFrame,2000);});
$('imgFile')?.addEventListener('change',async e=>{for(const f of e.target.files){const fd=new FormData();fd.append('image',f);const out=await postForm(cfg.frameUrl,fd);if(out.ok){renderResults(out.results,0);renderFeed(out.feed);}else alert(out.error)}e.target.value='';});
document.querySelectorAll('[data-demo]').forEach(b=>b.addEventListener('click',async()=>{
  const fd=new FormData();fd.append('kind',b.dataset.demo);const out=await postForm(cfg.demoUrl,fd);
  if(out.ok){renderResults(out.results,0);renderFeed(out.feed);}else alert(out.error);}));
let auto=null;$('btnAuto')?.addEventListener('click',()=>{const b=$('btnAuto');if(auto){clearInterval(auto);auto=null;b.textContent='Auto-simulate class';b.classList.replace('btn-danger','btn-outline-primary');}else{b.textContent='Stop auto-simulation';b.classList.replace('btn-outline-primary','btn-danger');auto=setInterval(()=>document.querySelector('[data-demo=student]').click(),1800);}});
async function poll(){try{const r=await fetch(cfg.feedUrl);renderFeed(await r.json());}catch(e){}}
poll();setInterval(poll,3000);
})();
