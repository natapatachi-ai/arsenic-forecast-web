// browser_pdf_extract.js
// เครื่องมือที่ใช้ถอดตารางจาก PDF รายงานคุณภาพน้ำครั้งที่ 24 ของ คพ. ภายในเบราว์เซอร์ (ครั้งเดียว, 24 พ.ย. 2569)
// ใช้เฉพาะ API ที่มีในเบราว์เซอร์ (fetch, DecompressionStream) ไม่โหลดสคริปต์ภายนอก
// วิธีใช้: เปิดหน้า https://epo01.pcd.go.th/th/information/more/358 แล้ววางโค้ดนี้ใน Console
//   const P = await window.__pdfx(urlของปุ่ม "ดูออนไลน์");   // ได้ chunks ข้อความพร้อมพิกัดทุกหน้า
//   window.__grid(P[22])                                      // ตารางสารหนู ปี 2568 (หน้า 23) แบบ station;R1;R2;...
// งานปกติให้ใช้ scripts/pcd_pdf_tables.py (Python + pdfplumber) แทน

window.__pdfx = async function(url){
  const buf = new Uint8Array(await fetch(url).then(r=>r.arrayBuffer()));
  let S=''; for(let i=0;i<buf.length;i+=65536) S+=String.fromCharCode.apply(null, buf.subarray(i,i+65536));
  const inflate = async (b)=>{ const ds=new DecompressionStream('deflate'); const w=ds.writable.getWriter(); w.write(b).catch(()=>{}); w.close().catch(()=>{}); const r=ds.readable.getReader(); const parts=[]; let tot=0; try{ while(true){ const {value,done}=await r.read(); if(done) break; parts.push(value); tot+=value.length; } }catch(e){} const out=new Uint8Array(tot); let o=0; for(const p of parts){ out.set(p,o); o+=p.length; } return out; };
  const b2s = (u)=>{let s='';for(let i=0;i<u.length;i+=65536) s+=String.fromCharCode.apply(null,u.subarray(i,i+65536));return s;};
  const objs={};
  const re=/(\d+)\s+0\s+obj\b/g; let m; const starts=[];
  while((m=re.exec(S))) starts.push([+m[1], m.index+m[0].length]);
  for(let k=0;k<starts.length;k++){
    const [num,st]=starts[k]; const end=S.indexOf('endobj',st); let body=S.slice(st,end<0?undefined:end);
    let dict=body, stream=null;
    const si=body.search(/stream\r?\n/);
    if(si>=0){ dict=body.slice(0,si); const ds=si+body.slice(si).match(/stream\r?\n/)[0].length; const de=body.lastIndexOf('endstream'); const abs=st+ds; const L=dict.match(/\/Length\s+(\d+)(?!\s+0\s+R)/); stream=L?buf.subarray(abs, abs+(+L[1])):buf.subarray(abs, st+de); }
    objs[num]={dict, stream};
  }
  const dec = async (o)=>{ if(!o.stream) return ''; if(o._d!==undefined) return o._d; let d; if(/FlateDecode/.test(o.dict)){ const u=await inflate(o.stream); d=u?b2s(u):''; } else d=b2s(o.stream); o._d=d; return d; };
  // object streams
  for(const n of Object.keys(objs)){ const o=objs[n]; if(/\/Type\s*\/ObjStm/.test(o.dict)){ const d=await dec(o); const N=+o.dict.match(/\/N\s+(\d+)/)[1]; const F=+o.dict.match(/\/First\s+(\d+)/)[1]; const hdr=d.slice(0,F).trim().split(/\s+/).map(Number); for(let i=0;i<N;i++){ const on=hdr[2*i], off=hdr[2*i+1]; const nx=i+1<N?hdr[2*i+3]:d.length-F; if(!objs[on]) objs[on]={dict:d.slice(F+off,F+nx), stream:null}; } } }
  const ref=(s)=>{ const mm=s&&s.match(/^\s*(\d+)\s+0\s+R/); return mm?objs[+mm[1]]:null; };
  const getVal=(dict,key)=>{ const i=dict.indexOf('/'+key); if(i<0) return null; return dict.slice(i+key.length+1); };
  const subDict=(s)=>{ s=s.trimStart(); if(s.startsWith('<<')){ let d=0; for(let i=0;i<s.length;i++){ if(s.startsWith('<<',i)){d++;i++;} else if(s.startsWith('>>',i)){d--;i++; if(d===0) return s.slice(0,i+1);} } } const r=ref(s); return r?r.dict:null; };
  const parseCMap=(t)=>{ const map={}; let mm; const hx=(h)=>{let s='';for(let i=0;i+3<h.length+0&&i<h.length;i+=4) s+=String.fromCharCode(parseInt(h.substr(i,4),16)); return s;};
    for(const blk of t.split('beginbfchar').slice(1)){ const b=blk.split('endbfchar')[0]; const r2=/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/g; while((mm=r2.exec(b))) map[parseInt(mm[1],16)]=hx(mm[2]); }
    for(const blk of t.split('beginbfrange').slice(1)){ const b=blk.split('endbfrange')[0]; const r3=/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])/g; while((mm=r3.exec(b))){ const a=parseInt(mm[1],16), z=parseInt(mm[2],16); if(mm[3][0]==='<'){ const base=mm[3].slice(1,-1); const bc=parseInt(base.slice(-4),16); const pre=hx(base.slice(0,-4)); for(let c=a;c<=z;c++) map[c]=pre+String.fromCharCode(bc+c-a);} else { const arr=mm[3].match(/<([0-9A-Fa-f]+)>/g)||[]; arr.forEach((h,i)=>map[a+i]=hx(h.slice(1,-1))); } } }
    return map; };
  const fontCache={};
  const loadFont=async(fdict)=>{ const tu=getVal(fdict,'ToUnicode'); let cmap={}; const r=tu&&ref(tu); if(r) cmap=parseCMap(await dec(r)); const two=/Type0/.test(fdict); const W={}; let DW=1000;
  if(two){ const df=fdict.match(/\/DescendantFonts\s*(\[\s*\d+\s+0\s+R\s*\]|\d+\s+0\s+R)/); let dd=null; if(df){ let o=ref(df[1].replace('[','')); if(o&&o.dict.trim().startsWith('[')) o=ref(o.dict.replace('[','')); dd=o?o.dict:null; }
    if(dd){ const dw=dd.match(/\/DW\s+(\d+)/); if(dw) DW=+dw[1]; let wv=getVal(dd,'W'); if(wv){ wv=wv.trimStart(); if(!wv.startsWith('[')){ const o=ref(wv); wv=o?o.dict:''; } let depth=0,end=0; for(let i=0;i<wv.length;i++){ if(wv[i]==='[')depth++; else if(wv[i]===']'){depth--; if(depth===0){end=i;break;}} } const body=wv.slice(1,end); const tk=body.match(/\[|\]|[+-]?\d*\.?\d+/g)||[]; let i=0; while(i<tk.length){ const c=+tk[i]; if(tk[i+1]==='['){ let j=i+2,k=0; while(tk[j]!==']'){ W[c+k]=+tk[j]; j++;k++; } i=j+1; } else { const c2=+tk[i+1], w=+tk[i+2]; for(let c3=c;c3<=c2;c3++) W[c3]=w; i+=3; } } } } }
  else { const fc=fdict.match(/\/FirstChar\s+(\d+)/); let wv=getVal(fdict,'Widths'); if(fc&&wv){ wv=wv.trimStart(); if(!wv.startsWith('[')){ const o=ref(wv); wv=o?o.dict:''; } const arr=wv.slice(1,wv.indexOf(']')).trim().split(/\s+/).map(Number); arr.forEach((w,i)=>W[+fc[1]+i]=w); DW=500; } }
  return {cmap,two,W,DW}; };
  // pages (ordered by /Pages /Kids)
  const pages=Object.values(objs).filter(o=>/\/Type\s*\/Page\b(?!s)/.test(o.dict));
  const root=Object.values(objs).find(o=>/\/Type\s*\/Pages\b/.test(o.dict)&&!/\/Parent/.test(o.dict));
  const ordered=[]; const walk=(o)=>{ if(/\/Type\s*\/Page\b(?!s)/.test(o.dict)){ordered.push(o);return;} const kids=o.dict.match(/\/Kids\s*\[([^\]]*)\]/); if(!kids) return; for(const k of kids[1].match(/\d+\s+0\s+R/g)) { const c=ref(k); if(c) walk(c);} };
  if(root) walk(root); const plist=ordered.length?ordered:pages;
  const result=[];
  for(let pi=0;pi<plist.length;pi++){
    const pg=plist[pi]; let res=getVal(pg.dict,'Resources'); res=res?subDict(res):'';
    let fonts={}; const fv=res&&getVal(res,'Font'); const fd=fv?subDict(fv):''; if(fd){ const r4=/\/([^\s\/<>\[\]]+)\s+(\d+)\s+0\s+R/g; let mm2; while((mm2=r4.exec(fd))){ const key=mm2[1]; const fo=objs[+mm2[2]]; if(!fo) continue; if(!fontCache[mm2[2]]) fontCache[mm2[2]]=await loadFont(fo.dict); fonts[key]=fontCache[mm2[2]]; } }
    const cv=getVal(pg.dict,'Contents'); let refs=[]; if(cv.trimStart().startsWith('[')) refs=cv.slice(0,cv.indexOf(']')).match(/\d+\s+0\s+R/g); else refs=[cv.match(/\d+\s+0\s+R/)[0]];
    let content=''; for(const r of refs){ content+=(await dec(ref(r)))+'\n'; }
    // tokenize content stream
    const toks=[]; const tr=/(<<|>>|\[|\]|\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|\/[^\s\/\[\]<>()]+|[+-]?\d*\.?\d+|[A-Za-z'"*]+[0-9]?\*?)/g; let t;
    while((t=tr.exec(content))) toks.push(t[1]);
    let ctm=[1,0,0,1,0,0], stack=[], tm=[1,0,0,1,0,0], tlm=[1,0,0,1,0,0], font=null, fs=1, lead=0; const ops=[]; const chunks=[];
    const mul=(a,b)=>[a[0]*b[0]+a[1]*b[2],a[0]*b[1]+a[1]*b[3],a[2]*b[0]+a[3]*b[2],a[2]*b[1]+a[3]*b[3],a[4]*b[0]+a[5]*b[2]+b[4],a[4]*b[1]+a[5]*b[3]+b[5]];
    const decStr=(s)=>{ let bytes=''; if(s[0]==='<'){ const h=s.slice(1,-1).replace(/\s/g,''); for(let i=0;i<h.length;i+=2) bytes+=String.fromCharCode(parseInt(h.substr(i,2),16)); } else { const inner=s.slice(1,-1); for(let i=0;i<inner.length;i++){ let c=inner[i]; if(c==='\\'){ const n=inner[++i]; if(/[0-7]/.test(n)){ let o=n; while(o.length<3&&/[0-7]/.test(inner[i+1])) o+=inner[++i]; bytes+=String.fromCharCode(parseInt(o,8)); } else bytes+=({n:'\n',r:'\r',t:'\t',b:'\b',f:'\f'}[n]||n); } else bytes+=c; } }
      let out=''; let wsum=0; if(font&&font.two){ for(let i=0;i+1<bytes.length;i+=2){ const code=(bytes.charCodeAt(i)<<8)|bytes.charCodeAt(i+1); out+=font.cmap[code]??''; wsum+=(font.W[code]??font.DW); } } else { for(let i=0;i<bytes.length;i++){ const c=bytes.charCodeAt(i); out+=(font&&font.cmap[c])??String.fromCharCode(c); wsum+=(font?(font.W[c]??font.DW):500);} } window.__lastW=wsum; return out; };
    const emit=(txt,wtot)=>{ const m2=mul(tm,ctm); const sc=Math.hypot(m2[0],m2[1]); chunks.push([Math.round(m2[4]*10)/10, Math.round(m2[5]*10)/10, txt, Math.round(fs*Math.hypot(m2[2],m2[3])*10)/10, Math.round((m2[4]+wtot/1000*fs*sc)*10)/10]); };
    for(const tk of toks){
      if(/^[A-Za-z'"*]/.test(tk) && !tk.startsWith('/')){
        const op=tk; const a=ops;
        if(op==='q') stack.push(ctm.slice()); else if(op==='Q') ctm=stack.pop()||ctm; else if(op==='cm') ctm=mul(a.slice(-6).map(Number),ctm);
        else if(op==='BT'){ tm=[1,0,0,1,0,0]; tlm=tm.slice(); }
        else if(op==='Tf'){ font=fonts[a[a.length-2].slice(1)]||null; fs=+a[a.length-1]; }
        else if(op==='Td'||op==='TD'){ const tx=+a[a.length-2], ty=+a[a.length-1]; if(op==='TD') lead=-ty; tlm=mul([1,0,0,1,tx,ty],tlm); tm=tlm.slice(); }
        else if(op==='Tm'){ tlm=a.slice(-6).map(Number); tm=tlm.slice(); }
        else if(op==='TL'){ lead=+a[a.length-1]; }
        else if(op==='T*'){ tlm=mul([1,0,0,1,0,-lead],tlm); tm=tlm.slice(); }
        else if(op==='Tj'||op==="'"||op==='"'){ if(op!=='Tj'){ tlm=mul([1,0,0,1,0,-lead],tlm); tm=tlm.slice(); } const s=a[a.length-1]; if(s){ const tx=decStr(s); emit(tx, window.__lastW); } }
        else if(op==='TJ'){ const i0=a.lastIndexOf('['); let txt=''; let wt=0; for(const x of a.slice(i0+1)){ if(x==='[') continue; if(x[0]==='('||x[0]==='<'){ txt+=decStr(x); wt+=window.__lastW; } else { wt-=+x; if(+x < -200) txt+=' '; } } emit(txt, wt); }
        ops.length=0;
      } else ops.push(tk);
    }
    result.push(chunks);
  }
  return result;
};

// รวม chunks เป็นบรรทัดข้อความ (ใช้อ่านเนื้อความ)
window.__lines = function(chunks, ytol){ ytol=ytol||2; const rows=[]; const cs=chunks.filter(c=>c[2].trim()!=='').sort((a,b)=>b[1]-a[1]||a[0]-b[0]); for(const c of cs){ let r=rows.find(r=>Math.abs(r.y-c[1])<=ytol); if(!r){ r={y:c[1],c:[]}; rows.push(r);} r.c.push(c);} rows.sort((a,b)=>b.y-a.y);
 return rows.map(r=>{ const c=r.c.sort((a,b)=>a[0]-b[0]); let s='', lastEnd=null, fs=c[0][3]||10; for(const k of c){ if(lastEnd!==null){ const gap=k[0]-lastEnd; s+= gap>2.0*fs ? ' | ' : (gap>0.2*fs ? ' ' : ''); } s+=k[2]; lastEnd=Math.max(lastEnd??-1e9,k[4]); } return s; }); };

// แถวข้อความแบบคั่นด้วย | (ใช้ตรวจหัวตาราง)
window.__rows = function(ch){ const cs=ch.filter(c=>c[2].trim()!==''); const ys=[]; for(const c of cs.sort((a,b)=>b[1]-a[1])){ let r=ys.find(r=>Math.abs(r.y-c[1])<2); if(!r){r={y:c[1],c:[]};ys.push(r);} r.c.push(c);} ys.sort((a,b)=>b.y-a.y); return ys.map(r=>r.c.sort((a,b)=>a[0]-b[0]).map(c=>c[2].trim()).join('|')); };

// ถอดตารางภาคผนวก: แถว = ระดับ y ของรหัสสถานี, คอลัมน์ = x ของเลขครั้งที่ในหัวตาราง
window.__grid = function(ch){
  const cs=ch.filter(c=>c[2].trim()!=='').map(c=>({x:c[0],y:c[1],t:c[2].trim()}));
  const byY={}; cs.forEach(c=>{ if(/^\d{1,2}$/.test(c.t)){ const k=Math.round(c.y); (byY[k]=byY[k]||[]).push(c);} });
  let hdr=Object.values(byY).sort((a,b)=>b.length-a.length)[0].sort((a,b)=>a.x-b.x);
  const H=[]; for(const c of hdr){ const last=H[H.length-1]; if(last && c.x-last.xe<3){ last.t+=c.t; last.xe=c.x+5; } else H.push({t:c.t,x:c.x,xe:c.x+5}); }
  const cols=H.map(h=>({r:+h.t,x:h.x}));
  const left=cs.filter(c=>c.x<cols[0].x-12); const g=[]; for(const c of left.sort((a,b)=>b.y-a.y||a.x-b.x)){ let r=g.find(r=>Math.abs(r.y-c.y)<1.5); if(!r){r={y:c.y,c:[]};g.push(r);} r.c.push(c);} const stations=[]; for(const r of g){ const txt=r.c.sort((a,b)=>a.x-b.x).map(z=>z.t).join(''); const m=txt.match(/(KK|FA|KO|LA|SU|SA|RU|NK)\d\d/); if(m) stations.push({id:m[0],y:r.y}); }
  const x0=cols[0].x-12; const vals=cs.filter(c=>c.x>=x0 && /^(<|\d|\.|-|ND)/.test(c.t) && c.y<hdr[0].y-3);
  const cell={};
  for(const v of vals){ let best=null,bd=1e9; for(const s of stations){ const d=Math.abs(s.y-v.y); if(d<bd){bd=d;best=s;} } if(!best||bd>7) continue; let ci=0,cd=1e9; cols.forEach((c,i)=>{ const d=Math.abs(c.x-v.x); if(d<cd){cd=d;ci=i;} }); const key=best.id+'@'+ci; (cell[key]=cell[key]||[]).push(v); }
  const lines=['station;'+cols.map(c=>'R'+c.r).join(';')];
  for(const s of stations){ lines.push(s.id+';'+cols.map((c,i)=>{ const a=(cell[s.id+'@'+i]||[]).sort((p,q)=>p.x-q.x); return a.map(z=>z.t).join(''); }).join(';')); }
  return lines.join('\n');
};
