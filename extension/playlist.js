const pl=id=>document.getElementById(id);
let playlistItems=[],playlistJob=null;
const formatChoices=[["mp3-192","MP3 192 kbps"],["mp3-128","MP3 128 kbps"],["mp3-320","MP3 320 kbps"],["m4a","M4A"],["best-mp4","MP4 en iyi"],["mp4-1080","MP4 1080p"],["mp4-720","MP4 720p"],["best-webm","WebM en iyi"],["best-mkv","MKV en iyi"]];
function playlistRender(){
 const root=pl("playlist-items");root.replaceChildren();
 for(const item of playlistItems){
  const row=document.createElement("div");row.className="playlist-row";
  const check=document.createElement("input");check.type="checkbox";check.checked=item.checked;check.onchange=()=>item.checked=check.checked;row.append(check);
  const img=document.createElement("img");img.src="https://i.ytimg.com/vi/"+item.id+"/mqdefault.jpg";row.append(img);
  const name=document.createElement("span");name.className="name";name.textContent=item.title;row.append(name);
  const select=document.createElement("select");for(const [value,label] of formatChoices){const option=document.createElement("option");option.value=value;option.textContent=label;select.append(option)}
  select.value=item.format_id;select.onchange=()=>item.format_id=select.value;row.append(select);root.append(row);
 }
}
function showTab(playlist){
 pl("video-panel").classList.toggle("hidden",playlist);
 pl("playlist-panel").classList.toggle("hidden",!playlist);
 pl("tab-videos").classList.toggle("active",!playlist);
 pl("tab-playlists").classList.toggle("active",playlist);
}
pl("tab-videos").onclick=()=>showTab(false);
pl("tab-playlists").onclick=()=>showTab(true);
pl("playlist-all").onclick=()=>{playlistItems.forEach(x=>x.checked=true);playlistRender()};
pl("playlist-none").onclick=()=>{playlistItems.forEach(x=>x.checked=false);playlistRender()};
pl("playlist-apply").onclick=()=>{playlistItems.forEach(x=>x.format_id=pl("playlist-format").value);playlistRender()};
async function loadPlaylist(url){
 pl("playlist-url").value=url;pl("playlist-message").textContent="Liste okunuyor…";
 try{
  const result=await post("/playlist",{url});
  playlistItems=(result.items||[]).map(x=>({...x,checked:true,format_id:"mp3-192"}));
  pl("playlist-title").textContent=result.title+" ("+playlistItems.length+" video)";
  pl("playlist-message").textContent=playlistItems.length>=300?"İlk 300 video listelendi.":"";
  playlistRender();showTab(true);
 }catch(e){pl("playlist-message").textContent="Liste hatası: "+clean(e)}
}
pl("playlist-load").onclick=()=>loadPlaylist(pl("playlist-url").value.trim());
pl("playlist-url").onkeydown=e=>{if(e.key==="Enter")loadPlaylist(e.target.value.trim())};
pl("playlist-download").onclick=async()=>{
 const items=playlistItems.filter(x=>x.checked).map(x=>({url:x.url,format_id:x.format_id}));
 if(!items.length){pl("playlist-message").textContent="Önce video seçin.";return}
 if(playlistJob){pl("playlist-message").textContent="İndirme zaten sürüyor.";return}
 try{
  const data=await post("/batch",{items});playlistJob=data.job_id;
  await chrome.storage.local.set({playlistJob});
  pl("playlist-message").textContent="Toplu indirme başladı.";
  pollPlaylist();
 }catch(e){pl("playlist-message").textContent="İndirme hatası: "+clean(e)}
};
async function pollPlaylist(){
 const id=playlistJob;if(!id)return;
 try{
  const response=await fetch(API+"/jobs/"+encodeURIComponent(id));const job=await response.json();
  if(!response.ok)throw Error(job.error||"Görev bulunamadı");
  pl("playlist-message").textContent="Tamamlanan: "+job.completed+" / "+job.total+" | Hatalı: "+job.failed+(job.current?" | İşleniyor: "+job.current:"");
  if(job.status==="done"){
   if(job.errors?.length)pl("playlist-message").textContent+="\n"+job.errors.join("\n");
   playlistJob=null;await chrome.storage.local.remove("playlistJob");return;
  }
  setTimeout(pollPlaylist,2500);
 }catch(e){pl("playlist-message").textContent="Durum alınamadı: "+clean(e);setTimeout(pollPlaylist,5000)}
}
(async()=>{
 const stored=await chrome.storage.local.get(["playlistJob","detectedPlaylist"]);
 if(stored.playlistJob){playlistJob=stored.playlistJob;pollPlaylist()}
 if(stored.detectedPlaylist){pl("playlist-url").value=stored.detectedPlaylist;showTab(true);loadPlaylist(stored.detectedPlaylist)}
})();
