(function(){
  const esc=s=>String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  function embedUrl(raw){
    try{
      const u=new URL(raw.trim());
      if(u.hostname.includes('youtube.com')){const id=u.searchParams.get('v');return id?`https://www.youtube.com/embed/${id}`:''}
      if(u.hostname==='youtu.be'){const id=u.pathname.split('/').filter(Boolean)[0];return id?`https://www.youtube.com/embed/${id}`:''}
      if(u.hostname.includes('aparat.com')){
        const parts=u.pathname.split('/').filter(Boolean); const idx=parts.indexOf('v'); const id=idx>=0?parts[idx+1]:'';
        return id?`https://www.aparat.com/video/video/embed/videohash/${id}/vt/frame`:'';
      }
    }catch(e){}
    return '';
  }
  function itemRow(item={}){return `<div class="feature-item-row">
    <span class="drag-handle">⋮⋮</span>
    <input class="form-control feature-item-title" placeholder="عنوان آیتم" value="${esc(item.title)}">
    <input class="form-control feature-item-image" dir="ltr" placeholder="آدرس تصویر (اختیاری)" value="${esc(item.image)}">
    <input class="form-control feature-item-link" dir="ltr" placeholder="لینک (اختیاری)" value="${esc(item.link)}">
    <button type="button" class="icon-remove" title="حذف">×</button>
  </div>`}
  function groupCard(group={title:'گروه جدید',items:[]}){return `<div class="feature-group-card">
    <div class="feature-group-head"><input class="form-control feature-group-title" value="${esc(group.title)}" placeholder="عنوان گروه"><button type="button" class="btn btn-sm btn-outline add-feature-item">+ آیتم</button><button type="button" class="icon-remove remove-group" title="حذف گروه">×</button></div>
    <div class="feature-items">${(group.items||[]).map(itemRow).join('')}</div>
  </div>`}
  const presets={
    perfume:[{title:'نت آغازی',items:[{title:'بادام'},{title:'فلفل'},{title:'انگور سیاه'}]},{title:'نت میانی',items:[{title:'گل برف'},{title:'گل یاس'},{title:'گل مریم'}]},{title:'رایحه ماندگار',items:[{title:'وانیل'},{title:'کهربا'},{title:'چوب صندل'}]}],
    fashion:[{title:'جنس و بافت',items:[{title:'پنبه'},{title:'لینن'}]},{title:'مناسب برای',items:[{title:'روزمره'},{title:'مهمانی'}]},{title:'راهنمای استایل',items:[{title:'استایل مینیمال'}]}],
    auto:[{title:'سازگاری با خودرو',items:[{title:'پژو ۲۰۶'},{title:'پژو ۲۰۷'}]},{title:'محل نصب',items:[{title:'موتور'},{title:'سیستم خنک‌کننده'}]},{title:'مزیت قطعه',items:[{title:'دوام بالا'}]}],
    mobile:[{title:'نمایشگر',items:[{title:'OLED'},{title:'۱۲۰ هرتز'}]},{title:'دوربین',items:[{title:'دوربین اصلی'},{title:'حالت شب'}]},{title:'عملکرد',items:[{title:'پردازنده'},{title:'باتری'}]}],
    blank:[{title:'گروه ویژگی',items:[{title:'آیتم نمونه'}]}]
  };
  document.addEventListener('DOMContentLoaded',()=>{
    document.querySelectorAll('.rich-enable').forEach(ch=>ch.addEventListener('change',()=>{document.getElementById(ch.dataset.target).hidden=!ch.checked}));
    const url=document.getElementById('productVideoUrl'), preview=document.getElementById('productVideoPreview');
    function updatePreview(){if(!url||!preview)return; const e=embedUrl(url.value);preview.innerHTML=e?`<iframe src="${e}" title="پیش‌نمایش ویدیو" loading="lazy" allowfullscreen></iframe>`:'<span>لینک معتبر آپارات یا YouTube وارد کنید.</span>'}
    url?.addEventListener('input',updatePreview);
    const builder=document.getElementById('featureGroupsBuilder');
    function setGroups(groups){builder.innerHTML=groups.map(groupCard).join('')}
    document.querySelectorAll('.rich-preset').forEach(b=>b.addEventListener('click',()=>setGroups(presets[b.dataset.preset])));
    document.getElementById('addFeatureGroup')?.addEventListener('click',()=>builder.insertAdjacentHTML('beforeend',groupCard()));
    builder?.addEventListener('click',e=>{
      const add=e.target.closest('.add-feature-item'); if(add){add.closest('.feature-group-card').querySelector('.feature-items').insertAdjacentHTML('beforeend',itemRow());return}
      const rem=e.target.closest('.icon-remove'); if(rem){const row=rem.closest('.feature-item-row'); if(row)row.remove(); else rem.closest('.feature-group-card')?.remove()}
    });
  });
})();