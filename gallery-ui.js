// My Gallery organization is local to the current account/browser.
var galleryPreferences={sort:'updated',pinned:[]};
var galleryDuplicateRequests=new Set();
var galleryActionMenuState=null;

function restoreGalleryPreferences() {
  var value=readLocalJson(accountKey('gallery'),null);
  galleryPreferences={sort:value && ['updated','created','name'].includes(value.sort) ? value.sort : 'updated',
    pinned:value && Array.isArray(value.pinned) ? Array.from(new Set(value.pinned.filter(function(id){return typeof id==='string';}))) : []};
}
function syncGalleryControls() {
  document.getElementById('gallery-sort-control').hidden=galleryTab==='public';
  var select=document.getElementById('gallery-sort');
  select.value=galleryPreferences.sort;select.disabled=accountStorageLoading;
}
function setGallerySort(order) {
  if(accountStorageLoading || !['updated','created','name'].includes(order))return;
  galleryPreferences.sort=order;writeLocalJson(accountKey('gallery'),galleryPreferences);renderGallery();
}
function isGalleryPinned(app) {
  return galleryPreferences.pinned.includes(String(app.urlId || app.id));
}
function toggleGalleryPin(id) {
  if(accountStorageLoading)return;
  var app=findMyAppByKey(id);
  if(!app || (app.uid && (!curUser || app.uid!==curUser.uid)))return;
  var key=String(app.urlId || app.id);
  if(isGalleryPinned(app))galleryPreferences.pinned=galleryPreferences.pinned.filter(function(value){return value!==key;});
  else galleryPreferences.pinned.push(key);
  writeLocalJson(accountKey('gallery'),galleryPreferences);renderGallery();
}
function galleryTime(value) {
  if(value && typeof value.toMillis==='function')return value.toMillis();
  var time=typeof value==='number' ? value : Number(new Date(value || 0));
  return Number.isFinite(time) ? time : 0;
}
function sortedMyGallery(list) {
  return list.map(function(app,index){return {app:app,index:index};}).sort(function(a,b) {
    var pinned=Number(isGalleryPinned(b.app))-Number(isGalleryPinned(a.app));
    if(pinned)return pinned;
    if(galleryPreferences.sort==='name') {
      var name=String(a.app.title || '').localeCompare(String(b.app.title || ''),uiLanguage==='en' ? 'en' : 'ja',{numeric:true,sensitivity:'base'});
      if(name)return name;
    } else {
      var field=galleryPreferences.sort==='created' ? 'createdAt' : 'updatedAt';
      var at=galleryTime(a.app[field] || a.app.savedAt || a.app.createdAt);
      var bt=galleryTime(b.app[field] || b.app.savedAt || b.app.createdAt);
      if(at!==bt)return bt-at;
    }
    return b.index-a.index;
  }).map(function(item){return item.app;});
}
function galleryAction(parent,className,label,content,handler) {
  var button=document.createElement('button');button.type='button';button.className=className;
  button.setAttribute('data-i18n-title',label);button.setAttribute('data-i18n-aria-label',label);
  button.title=t(label);button.setAttribute('aria-label',t(label));button.innerHTML=content;
  button.addEventListener('click',function(event){event.stopPropagation();handler();});parent.appendChild(button);
  return button;
}
function galleryButtonLabel(button,label) {
  var span=document.createElement('span');span.setAttribute('data-i18n',label);span.textContent=t(label);button.appendChild(span);
}
function closeGalleryActionMenu(restoreFocus) {
  var state=galleryActionMenuState;galleryActionMenuState=null;
  var menu=document.getElementById('gallery-action-menu');
  if(menu){menu.hidden=true;menu.textContent='';}
  if(state){state.trigger.setAttribute('aria-expanded','false');if(restoreFocus && state.trigger.isConnected)state.trigger.focus({preventScroll:true});}
}
function openGalleryActionMenu(trigger,app) {
  if(galleryActionMenuState && galleryActionMenuState.trigger===trigger){closeGalleryActionMenu(true);return;}
  closeGalleryActionMenu(false);
  var menu=document.getElementById('gallery-action-menu'),key=app.urlId || app.id;
  galleryActionMenuState={trigger:trigger};trigger.setAttribute('aria-expanded','true');
  function item(className,label,icon,handler) {
    var button=galleryAction(menu,'gc-menu-item '+className,label,icon,function(){closeGalleryActionMenu(true);handler();});
    button.setAttribute('role','menuitem');button.tabIndex=-1;galleryButtonLabel(button,label);return button;
  }
  item('gc-menu-rename','名前を変更','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16 4l4 4L8 20l-5 1 1-5Z"/></svg>',function(){openRenameApp(key);});
  var update=item('gc-update','ファイルで更新・比較','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/></svg>',function(){openAppComparison(key);});
  update.disabled=accountStorageLoading;
  var duplicate=item('gc-duplicate','複製する','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/></svg>',function(){duplicateMyApp(key);});
  duplicate.disabled=accountStorageLoading || galleryDuplicateRequests.has(accountRevision+'/'+key);
  item('gc-menu-danger','削除する','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15"/></svg>',function(){delApp(key);});
  menu.hidden=false;
  var rect=trigger.getBoundingClientRect(),width=menu.offsetWidth,height=menu.offsetHeight;
  menu.style.left=Math.max(8,Math.min(rect.right-width,window.innerWidth-width-8))+'px';
  menu.style.top=Math.max(8,rect.bottom+height+8<=window.innerHeight-8 ? rect.bottom+8 : rect.top-height-8)+'px';
  menu.querySelector('button:not(:disabled)').focus({preventScroll:true});
}
document.addEventListener('pointerdown',function(event) {
  var state=galleryActionMenuState,menu=document.getElementById('gallery-action-menu');
  if(state && !state.trigger.contains(event.target) && !menu.contains(event.target))closeGalleryActionMenu(false);
});
document.addEventListener('keydown',function(event) {
  if(!galleryActionMenuState)return;
  if(event.key==='Escape'){event.preventDefault();closeGalleryActionMenu(true);return;}
  if(event.key==='Tab'){closeGalleryActionMenu(true);return;}
  var menu=document.getElementById('gallery-action-menu');
  if(!menu.contains(event.target))return;
  var buttons=Array.from(menu.querySelectorAll('button:not(:disabled)')),index=buttons.indexOf(document.activeElement);
  if(event.key==='ArrowDown')index=(index+1)%buttons.length;
  else if(event.key==='ArrowUp')index=(index-1+buttons.length)%buttons.length;
  else if(event.key==='Home')index=0;
  else if(event.key==='End')index=buttons.length-1;
  else return;
  event.preventDefault();buttons[index].focus();
});
document.addEventListener('scroll',function(event) {
  var menu=document.getElementById('gallery-action-menu');
  if(galleryActionMenuState && !menu.contains(event.target))closeGalleryActionMenu(false);
},true);
window.addEventListener('resize',function(){closeGalleryActionMenu(false);});
function decorateMyGalleryCard(card,app) {
  var key=app.urlId || app.id, actions=card.querySelector('.gc-actions'),pinned=isGalleryPinned(app);
  card.dataset.appId=String(key);card.classList.toggle('gc-pinned',pinned);
  var edit=galleryAction(actions,'gc-edit','この作品を編集','',function(){editMyApp(key);});galleryButtonLabel(edit,'編集する');
  var more=galleryAction(actions,'gc-more','その他の操作','<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>',function(){openGalleryActionMenu(more,app);});
  galleryButtonLabel(more,'その他');more.setAttribute('aria-haspopup','menu');more.setAttribute('aria-controls','gallery-action-menu');more.setAttribute('aria-expanded','false');
  more.addEventListener('keydown',function(event){
    if(event.key!=='ArrowDown' && event.key!=='ArrowUp')return;
    event.preventDefault();event.stopPropagation();openGalleryActionMenu(more,app);
    if(event.key==='ArrowUp'){var buttons=document.querySelectorAll('#gallery-action-menu button:not(:disabled)');if(buttons.length)buttons[buttons.length-1].focus();}
  });
  var pin=galleryAction(card,'gc-pin',pinned ? 'ピン留めを解除' : 'ピン留め','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m16 3 5 5-5 2-2 5-2 2-5-5 2-2 5-2ZM8 16l-5 5"/></svg>',function(){
    var focused=document.activeElement===pin;toggleGalleryPin(key);
    if(focused){var next=Array.from(document.querySelectorAll('#gg .gc')).find(function(node){return node.dataset.appId===String(key);});if(next)next.querySelector('.gc-pin').focus({preventScroll:true});}
  });
  galleryButtonLabel(pin,pinned ? 'ピン留め済み' : 'ピン留め');
  pin.setAttribute('aria-pressed',String(pinned));pin.disabled=accountStorageLoading;
}
async function duplicateMyApp(id) {
  var revision=accountRevision,token=revision+'/'+id;
  if(galleryDuplicateRequests.has(token))return false;
  galleryDuplicateRequests.add(token);
  try {
    await accountStorageReady;if(revision!==accountRevision)return false;
    var source=findMyAppByKey(id);
    if(!source || typeof source.code!=='string' || (source.uid && (!curUser || source.uid!==curUser.uid)))return false;
    var base=source.title || inferAppTitle(source.code),suffix=t('のコピー'),n=1,title;
    do {
      var number=n===1 ? '' : ' '+n;
      title=base.slice(0,Math.max(1,100-suffix.length-number.length))+suffix+number;n++;
    } while(apps.some(function(app){return app.title===title;}));
    var copyId;do {copyId=generateId(10);}while(findMyAppByKey(copyId));
    var uid=curUser ? curUser.uid : null,now=Date.now();
    var copy={id:copyId,urlId:copyId,uid:uid || '',title:title,code:source.code,author:prof.name || '',avatar:prof.avatar || '',
      likes:0,createdAt:now,updatedAt:now,pendingCloud:!!uid};
    apps.push(copy);persistApps();renderGallery();
    var localOK=await waitForLocalWrites([accountKey('apps')]);
    if(revision!==accountRevision)return false;
    var saved=uid ? await autoSaveToFirestore(title,copyId,copy.code) : localOK;
    if(revision!==accountRevision)return false;
    T(t(saved ? '作品を複製しました' : '複製の保存に失敗しました。保存状況を確認してください'));
    return saved ? copyId : false;
  } finally {
    galleryDuplicateRequests.delete(token);
    if(revision===accountRevision)renderGallery();
  }
}

// Names are inferred from inert markup; parsing never executes the imported app.
function isAutomaticAppTitle(title) {
  return !String(title || '').trim() || /^(貼り付けコード|Pasted code|保存済みアプリ|Saved app)$/i.test(String(title).trim());
}
function inferAppTitle(code, fileName, createdAt) {
  var markup = document.createElement('template');
  markup.innerHTML = String(code || '');
  function text(selector) {
    var el=markup.content.querySelector(selector);
    return el ? (el.textContent || '').replace(/\s+/g,' ').trim().slice(0,100) : '';
  }
  var title=/\.(js|css)$/i.test(fileName || '') ? '' : text('title');
  if (title && !/^(untitled|document|無題)$/i.test(title) && !isAutomaticAppTitle(title)) return title;
  var base=String(fileName || '').replace(/\.(html?|js|css|txt)$/i,'').trim();
  if (base && !/^(index|untitled)$/i.test(base)) return base.slice(0,100);
  var heading=text('h1');
  if (heading && !isAutomaticAppTitle(heading)) return heading;
  var date=new Date(createdAt || Date.now());
  if (isNaN(date.getTime())) date=new Date();
  return t('作品')+' '+date.toLocaleString(uiLanguage==='en' ? 'en-US' : 'ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function chooseWorkTitle(code, candidate, fileName) {
  return isAutomaticAppTitle(candidate) ? inferAppTitle(code,fileName) : String(candidate).trim().slice(0,100);
}
function normalizeGalleryTitles() {
  var changed=false;
  apps.forEach(function(app) {
    if (isAutomaticAppTitle(app.title)) {
      app.title=inferAppTitle(app.code,app.sourceFileName,app.createdAt);changed=true;
    }
  });
  if (changed) persistApps();
}
function backToGallery() {
  flushStudioDraft();
  if (isFsS) toggleFS();
  nav('gallery');
  document.getElementById('workspace').style.display='none';
  var iframe=document.getElementById('sif');iframe.srcdoc='';iframe.removeAttribute('src');
  hideCP();updateTopNavVisibility();
}

// Render visible cards briefly in opaque-origin sandboxes, then retain only a
// script-free SVG image. Images are an in-memory cache, never uploaded to Firestore.
var galleryThumbnailCache=new Map();
var galleryThumbnailObserver=null;
var galleryThumbnailQueue=[];
var galleryThumbnailJobs=new Map();
var galleryThumbnailGeneration=0;
var galleryThumbnailCounter=0;

function thumbnailReporter(token) {
  function capture() {
    try {
      var clone=document.documentElement.cloneNode(true);
      // SVG image documents resolve viewport units differently from normal pages.
      function pixels(css) {
        return css.replace(/(-?[\d.]+)([dsl]?vh|[dsl]?vw|vmin|vmax)\b/gi,function(_,value,unit) {
          var size=/vh$/i.test(unit) ? 500 : /vw$/i.test(unit) ? 800 : unit.toLowerCase()==='vmin' ? 500 : 800;
          return (Number(value)*size/100)+'px';
        });
      }
      clone.querySelectorAll('style').forEach(function(style){style.textContent=pixels(style.textContent);});
      clone.querySelectorAll('[style]').forEach(function(el){el.setAttribute('style',pixels(el.getAttribute('style')));});
      clone.style.width='800px';clone.style.height='500px';
      var body=clone.querySelector('body'), computed=getComputedStyle(document.body);
      if(body){body.style.width=computed.width;body.style.height=computed.height;}
      var rootBackground=getComputedStyle(document.documentElement).backgroundColor;
      clone.style.backgroundColor=rootBackground==='rgba(0, 0, 0, 0)' ? computed.backgroundColor : rootBackground;

      var canvases=document.querySelectorAll('canvas');
      clone.querySelectorAll('canvas').forEach(function(canvas,index) {
        try {
          var image=document.createElement('img');
          Array.from(canvas.attributes).forEach(function(attr){image.setAttribute(attr.name,attr.value);});
          var canvasStyle=getComputedStyle(canvases[index]);
          ['width','height','display','background-color','border','border-radius','box-shadow','position','top','left','right','bottom','margin','padding','transform','transform-origin','z-index','opacity','box-sizing'].forEach(function(property) {
            image.style.setProperty(property,canvasStyle.getPropertyValue(property));
          });
          image.src=canvases[index].toDataURL('image/png');canvas.replaceWith(image);
        } catch(e) {}
      });
      clone.querySelectorAll('script,iframe,object,embed,link,meta,base,audio,video').forEach(function(el){el.remove();});
      clone.querySelectorAll('*').forEach(function(el) {
        Array.from(el.attributes).forEach(function(attr) {
          if (/^on/i.test(attr.name) || attr.name==='srcdoc' || attr.name==='href')el.removeAttribute(attr.name);
        });
        if(el.hasAttribute('src') && !/^data:image\//i.test(el.getAttribute('src')))el.removeAttribute('src');
      });
      var svg='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><foreignObject width="100%" height="100%">'+new XMLSerializer().serializeToString(clone)+'</foreignObject></svg>';
      var image='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
      parent.postMessage({type:'__poteto_thumbnail__',token:token,image:image.length<=1500000 ? image : null},'*');
    } catch(e) { parent.postMessage({type:'__poteto_thumbnail__',token:token,image:null},'*'); }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){setTimeout(capture,250);});
  else setTimeout(capture,250);
}
function buildThumbnailDocument(code, token, allowAppScripts) {
  // Templates are inert, unlike DOMParser documents which can fetch image URLs
  // during parsing. Temporary wrapper tags preserve html/head/body attributes.
  var source=normalizeGalleryPreviewCode(code || '');
  var wrapperTags={html:'div',head:'section',body:'main'};
  source=source.replace(/<!--[\s\S]*?-->|<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>|<(\/?)(html|head|body)\b((?:"[^"]*"|'[^']*'|[^'">])*)>/gi,function(all,raw,closing,tag,attrs) {
    if(raw || all.startsWith('<!--'))return all;
    tag=tag.toLowerCase();
    return '<'+closing+wrapperTags[tag]+(closing ? '' : ' data-pts-structure="'+tag+'"'+attrs)+'>';
  });
  var template=document.createElement('template');template.innerHTML=source;
  var content=template.content;
  content.querySelectorAll('meta[http-equiv],base,iframe,object,embed,audio,video,link').forEach(function(el){el.remove();});
  if(!allowAppScripts) {
    content.querySelectorAll('script').forEach(function(el){el.remove();});
    content.querySelectorAll('*').forEach(function(el){Array.from(el.attributes).forEach(function(attr){if(/^on/i.test(attr.name))el.removeAttribute(attr.name);});});
  }
  // Do not rely on a meta policy alone to stop speculative resource preloads.
  content.querySelectorAll('script[src]').forEach(function(el){el.remove();});
  content.querySelectorAll('[src],[srcset],[poster],[background]').forEach(function(el) {
    el.removeAttribute('srcset');
    ['src','poster','background'].forEach(function(attr) {
      if(el.hasAttribute(attr) && !/^(data:image\/|blob:)/i.test(el.getAttribute(attr)))el.removeAttribute(attr);
    });
  });
  var html=content.querySelector('[data-pts-structure="html"]');
  var head=content.querySelector('[data-pts-structure="head"]');
  var body=content.querySelector('[data-pts-structure="body"]');
  function attributes(el) {
    return el ? Array.from(el.attributes).filter(function(attr){return attr.name!=='data-pts-structure';}).map(function(attr){return ' '+attr.name+'="'+E(attr.value)+'"';}).join('') : '';
  }
  var bodyTemplate=document.createElement('template');
  Array.from((html || content).childNodes).forEach(function(node) {
    if(node===head)return;
    if(node===body)Array.from(body.childNodes).forEach(function(child){bodyTemplate.content.appendChild(child.cloneNode(true));});
    else bodyTemplate.content.appendChild(node.cloneNode(true));
  });
  var policy="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; media-src 'none'; base-uri 'none'; form-action 'none'";
  var report='<scr'+'ipt>('+thumbnailReporter.toString()+')('+JSON.stringify(token)+');</scr'+'ipt>';
  return '<!DOCTYPE html><html'+attributes(html)+'><head><meta http-equiv="Content-Security-Policy" content="'+policy+'">'+report+(head ? head.innerHTML : '')+'</head><body'+attributes(body)+'>'+bodyTemplate.innerHTML+'</body></html>';
}
function stopGalleryThumbnails(clearCache) {
  galleryThumbnailGeneration++;
  if(galleryThumbnailObserver)galleryThumbnailObserver.disconnect();
  galleryThumbnailQueue=[];
  galleryThumbnailJobs.forEach(function(job){clearTimeout(job.timeout);job.iframe.remove();});
  galleryThumbnailJobs.clear();
  if(clearCache)galleryThumbnailCache.clear();
}
function showThumbnailImage(host,image,title) {
  host.replaceChildren();
  var img=document.createElement('img');img.className='gc-preview';img.alt=t('画面プレビュー')+': '+(title || '');img.src=image;
  host.appendChild(img);
}
function finishThumbnail(token,image) {
  var job=galleryThumbnailJobs.get(token);
  if(!job)return;
  clearTimeout(job.timeout);job.iframe.remove();galleryThumbnailJobs.delete(token);
  if(job.generation===galleryThumbnailGeneration && job.host.isConnected) {
    if(typeof image==='string' && image.length<=1500000 && image.startsWith('data:image/svg+xml;charset=utf-8,')) {
      galleryThumbnailCache.delete(job.key);galleryThumbnailCache.set(job.key,{code:job.code,image:image});
      while(galleryThumbnailCache.size>24)galleryThumbnailCache.delete(galleryThumbnailCache.keys().next().value);
      showThumbnailImage(job.host,image,job.title);
    } else {
      job.host.replaceChildren();var label=document.createElement('span');label.className='gc-preview-note';
      label.setAttribute('data-i18n','開いて画面を見る');label.textContent=t('開いて画面を見る');job.host.appendChild(label);
    }
  }
  drainThumbnailQueue();
}
function drainThumbnailQueue() {
  while(galleryThumbnailJobs.size<3 && galleryThumbnailQueue.length) {
    var item=galleryThumbnailQueue.shift();
    if(!item.host.isConnected || !document.getElementById('view-gallery').classList.contains('active'))continue;
    var token=String(++galleryThumbnailCounter);
    var iframe=document.createElement('iframe');iframe.className='gc-preview-frame';
    iframe.setAttribute('sandbox','allow-scripts');iframe.setAttribute('aria-hidden','true');iframe.tabIndex=-1;
    iframe.setAttribute('allow',"autoplay 'none'; camera 'none'; microphone 'none'; geolocation 'none'");
    iframe.referrerPolicy='no-referrer';
    iframe.style.transform='scale('+(item.host.clientWidth/800)+')';
    item.host.appendChild(iframe);
    var job=Object.assign({},item,{iframe:iframe,generation:galleryThumbnailGeneration});
    galleryThumbnailJobs.set(token,job);
    job.timeout=setTimeout(function(id){return function(){finishThumbnail(id,null);};}(token),2500);
    iframe.srcdoc=buildThumbnailDocument(item.code,token,item.allowAppScripts);
  }
}
function attachGalleryThumbnail(host,app,isPublic) {
  var code=app.code || '',key=accountKey('thumbnail')+'|'+(isPublic?'public:':'my:')+(app._docId || app.urlId || app.id);
  var cached=galleryThumbnailCache.get(key);
  if(cached && cached.code===code){showThumbnailImage(host,cached.image,app.title);return;}
  var label=document.createElement('span');label.className='gc-preview-note';label.setAttribute('data-i18n','プレビューを準備中');label.textContent=t('プレビューを準備中');host.appendChild(label);
  host._thumbnail={host:host,code:code,key:key,title:app.title,allowAppScripts:!isPublic};
  if(!galleryThumbnailObserver) {
    galleryThumbnailObserver=new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if(!entry.isIntersecting)return;
        var item=entry.target._thumbnail;
        if(item){galleryThumbnailObserver.unobserve(entry.target);galleryThumbnailQueue.push(item);}
      });
      drainThumbnailQueue();
    },{root:document.getElementById('g-body')});
  }
  galleryThumbnailObserver.observe(host);
}
window.addEventListener('message',function(event) {
  if(!event.data || event.data.type!=='__poteto_thumbnail__')return;
  var job=galleryThumbnailJobs.get(event.data.token);
  if(!job || event.source!==job.iframe.contentWindow)return;
  finishThumbnail(event.data.token,event.data.image);
});
