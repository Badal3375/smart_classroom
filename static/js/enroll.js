(function(){
const cfg=window.ENROLL_CFG;const $=id=>document.getElementById(id);
const video=$('video');let stream=null;
function msg(el,out){el.className='alert alert-'+(out.ok?'success':'warning')+' mt-2 py-2 small';el.innerHTML=(out.ok?`Saved ${out.saved} template(s). Total: ${out.total}.`:(out.error||'Nothing saved.'))+(out.rejected&&out.rejected.length?'<br>Rejected: '+out.rejected.join('; '):'');}
$('btnCam').onclick=async()=>{stream=await startCamera(video);if(stream)$('capBtns').classList.remove('d-none');};
async function capture(kind,n,delay){
  const imgs=[];const status=$(kind+'Msg');
  for(let i=0;i<n;i++){imgs.push(grab(video,800).url);status.textContent=`Captured ${i+1}/${n}...`;await new Promise(r=>setTimeout(r,delay));}
  const body={images:imgs};
  const url=kind=='face'?cfg.faceUrl:cfg.irisUrl;
  const out=await postJSON(url,body);msg(status,out);if(out.ok)setTimeout(()=>location.reload(),1500);
}
$('capFace').onclick=()=>capture('face',5,500);
$('capIris').onclick=()=>capture('iris',3,700);
['face','iris'].forEach(k=>$(k+'File').addEventListener('change',async e=>{
  const fd=new FormData();[...e.target.files].forEach(f=>fd.append('images',f));
  if(k=='face'&&$('fallback')?.checked)fd.append('fallback','1');
  if(k=='iris')fd.append('eye',$('eyeSide').value);
  const out=await postForm(k=='face'?cfg.faceUrl:cfg.irisUrl,fd);msg($(k+'Msg'),out);if(out.ok)setTimeout(()=>location.reload(),1500);}));
})();
