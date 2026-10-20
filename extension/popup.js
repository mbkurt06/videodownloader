const $=id=>document.getElementById(id);
const API='http://127.0.0.1:8765';
let videos=[], states=new Map();
function normalize(input){try{const u=new URL(input);if(!['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtu.be'].includes(u.hostname))return null;const id=u.hostname==='youtu.be'?u.pathname.slice(1):u.pathname.startsWith('/shorts/')?u.pathname.split('/')[2]:u.searchParams.get('v');return /^[a-zA-Z0-9_-]{11}$/.test(id||'')?{id,url:'https://www.youtube.com/watch?v='+id}:null}catch{return null}}
function clean(e){return String(e?.message||e).replace(/\x1b\[[0-9;]*m/g,'')}
async function post(path,body){const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(j.error||'Sunucu hatası');return j}
function render(){
 const root=$('videos');root.replaceChildren();
 if(!videos.length){root.textContent='Henüz video yok. YouTube\'da video açın.';return}
 for(const v of videos){
  const state=states.get(v.id)||{status:'loading',formats:[],message:'Formatlar aranıyor…'};
  const card=document.createElement('article');card.className='card';
  const thumb=document.createElement('img');thumb.className='thumb';thumb.src='https://i.ytimg.com/vi/'+v.id+'/mqdefault.jpg';thumb.alt='Video kapağı';card.append(thumb);
  const body=document.createElement('div');body.className='body';
  const title=document.createElement('div');title.className='title';title.textContent=(v.title||'YouTube videosu').replace(/ - YouTube$/,'');body.append(title);
  const controls=document.createElement('div');controls.className='controls';
  const select=document.createElement('select');select.setAttribute('aria-label','İndirme formatı');
  if(state.formats.length){for(const f of state.formats){const option=document.createElement('option');option.value=f.id;option.textContent=f.label;select.append(option)}select.value=state.selected||state.formats[0].id;select.onchange=()=>{state.selected=select.value}}
  else{const option=document.createElement('option');option.textContent=state.status==='loading'?'Formatlar aranıyor…':'Format alınamadı';select.append(option);select.disabled=true}
  controls.append(select);
  const btn=document.createElement('button');btn.className='download';btn.textContent='↓ Download';btn.disabled=!state.formats.length||state.status==='downloading';btn.onclick=()=>download(v,select.value);controls.append(btn);body.append(controls);
  const msg=document.createElement('div');msg.className='message';msg.textContent=state.message||'';body.append(msg);card.append(body);
  const remove=document.createElement('button');remove.className='remove';remove.textContent='×';remove.title='Videoyu kaldır';remove.onclick=async()=>{videos=videos.filter(item=>item.id!==v.id);states.delete(v.id);await chrome.storage.local.set({videos});render()};card.append(remove);root.append(card);
 }
}
async function inspect(v){
 const existing=states.get(v.id);if(existing&&['loading','ready','downloading','done'].includes(existing.status))return;
 const state={status:'loading',formats:[],selected:'',message:'Formatlar sorgulanıyor…'};states.set(v.id,state);render();
 try{const data=await post('/info',{url:v.url});state.formats=data.formats||[];state.status='ready';state.message=state.formats.length?'':'Uygun format bulunamadı';if(data.title&&(!v.title||v.title==='YouTube videosu')){v.title=data.title;await chrome.storage.local.set({videos})}}
 catch(e){state.status='error';state.message='Format hatası: '+clean(e)}
 render();
}
async function download(v,format_id){
 const state=states.get(v.id);state.selected=format_id;state.status='downloading';state.message='İndirme başlatılıyor…';render();
 try{const {job_id}=await post('/download',{url:v.url,format_id});for(let i=0;i<720;i++){await new Promise(resolve=>setTimeout(resolve,2000));const response=await fetch(API+'/jobs/'+encodeURIComponent(job_id));const job=await response.json();if(job.status==='done'){state.status='done';state.message='Tamamlandı: '+job.file;render();return}if(job.status==='error')throw Error(job.error);state.message='İndiriliyor / dönüştürülüyor…';render()}throw Error('Zaman aşımı')}
 catch(e){state.status='error';state.message='İndirme hatası: '+clean(e);render()}
}
async function load(){const data=await chrome.storage.local.get('videos');const ids=new Set();videos=(data.videos||[]).filter(v=>{if(!v.id||ids.has(v.id))return false;ids.add(v.id);return true});render();for(const v of videos)inspect(v)}
$('clear').onclick=async()=>{videos=[];states.clear();await chrome.storage.local.set({videos:[]});render()};
$('url').addEventListener('keydown',async e=>{if(e.key!=='Enter')return;const item=normalize(e.target.value);if(!item){$('status').textContent='Geçerli YouTube video bağlantısı girin';return}videos=[{...item,title:'YouTube videosu',seen:Date.now()},...videos.filter(v=>v.id!==item.id)].slice(0,100);await chrome.storage.local.set({videos});$('url').value='';$('status').textContent='';render();inspect(videos[0])});
chrome.storage.onChanged.addListener((changes,area)=>{if(area!=='local'||!changes.videos)return;const old=new Set(videos.map(v=>v.id));videos=changes.videos.newValue||[];render();for(const v of videos)if(!old.has(v.id))inspect(v)});
load();
