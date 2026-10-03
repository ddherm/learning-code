
const $=s=>document.querySelector(s);const key=document.body.dataset.storageKey;
function toast(s){const t=$('.toast');t.textContent=s;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000)}
const codeStatus=document.createElement('div');codeStatus.className='sr-only';codeStatus.setAttribute('role','status');document.body.append(codeStatus);
let activeStep=null;
function clearCodeSelection(){
  if(activeStep)activeStep.setAttribute('aria-pressed','false');
  document.querySelectorAll('.code-line.is-highlighted').forEach(line=>line.classList.remove('is-highlighted'));
  activeStep=null;codeStatus.textContent='已取消代码高亮';
}
document.querySelectorAll('.explanation-step').forEach(button=>button.addEventListener('click',()=>{
  const wasActive=activeStep===button;clearCodeSelection();if(wasActive)return;
  const card=button.closest('.code-card');const targets=[];
  button.dataset.lines.split(',').forEach(range=>{
    const [start,end=start]=range.split('-').map(Number);
    for(let n=start;n<=end;n++){const line=card.querySelector('.code-line[data-line="'+n+'"]');if(line)targets.push(line)}
  });
  if(!targets.length)return;
  activeStep=button;button.setAttribute('aria-pressed','true');
  targets.forEach(line=>line.classList.add('is-highlighted'));
  const label=button.querySelector('.step-hint').textContent.replace('↖ 对应代码 ','');
  codeStatus.textContent='已高亮 '+card.querySelector('h3').textContent+'，'+label;
  const pane=card.querySelector('.code-pane');pane.scrollLeft=0;
  const first=targets[0].getBoundingClientRect(),last=targets[targets.length-1].getBoundingClientRect();
  const top=document.querySelector('.toolbar').getBoundingClientRect().height+24;
  const bottom=innerHeight-24;
  if(first.top<top||first.top>bottom||last.bottom>bottom){
    const space=Math.max(0,bottom-top),height=last.bottom-first.top;
    const desired=top+Math.max(0,(space-Math.min(height,space))/2);
    window.scrollBy({top:first.top-desired,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  }
}));
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&activeStep){clearCodeSelection();event.preventDefault()}});
$('#wrap').onclick=()=>{document.body.classList.toggle('wrap-code');$('#wrap').textContent=document.body.classList.contains('wrap-code')?'恢复横向滚动':'代码折行'};
$('#wide').onclick=()=>{document.body.classList.toggle('full-width');$('#wide').textContent=document.body.classList.contains('full-width')?'显示目录':'加宽阅读'};
$('#expand').onclick=()=>{const items=[...document.querySelectorAll('details')];const open=items.some(x=>!x.open);items.forEach(x=>x.open=open);$('#expand').textContent=open?'收起选读':'展开选读'};
document.querySelectorAll('.copy').forEach(b=>b.onclick=async()=>{const t=[...document.querySelectorAll('#'+b.dataset.copy+' .line-src')].map(x=>x.textContent).join('\n');try{await navigator.clipboard.writeText(t);toast('代码已复制，保留原始缩进')}catch{const a=document.createElement('textarea');a.value=t;document.body.append(a);a.select();document.execCommand('copy');a.remove();toast('代码已复制')}});
document.querySelectorAll('[data-save]').forEach(e=>{try{e.value=localStorage.getItem(key+e.dataset.save)||''}catch{}e.addEventListener('input',()=>{try{localStorage.setItem(key+e.dataset.save,e.value)}catch{}})});
$('#export').onclick=()=>{let text='# '+document.title+' · 学习笔记与个人回答\n\n';document.querySelectorAll('.question').forEach(q=>{text+='## '+q.querySelector('h3').textContent+'\n\n'+q.querySelector('p').textContent+'\n\n'+q.querySelector('textarea').value+'\n\n'});text+='## 学习笔记\n\n'+$('[data-save="notes"]').value+'\n';const u=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download=document.body.dataset.lessonId+'-我的学习笔记.md';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
$('#print').onclick=()=>window.print();let printStates=[];window.addEventListener('beforeprint',()=>{printStates=[...document.querySelectorAll('details')].map(d=>d.open);document.querySelectorAll('details').forEach(d=>d.open=true)});window.addEventListener('afterprint',()=>document.querySelectorAll('details').forEach((d,i)=>d.open=printStates[i]));
const observer=new IntersectionObserver(es=>{for(const e of es){if(e.isIntersecting){document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+e.target.id))}}},{rootMargin:'-10% 0px -70% 0px'});document.querySelectorAll('main section').forEach(s=>observer.observe(s));
