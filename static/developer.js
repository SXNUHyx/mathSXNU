/* Developer-only table; user-provided values always enter the DOM as text. */
(() => {
  const root=document.querySelector('#developer-users');
  if (!root) return;
  const q=s=>document.querySelector(s), form=q('#manager-filter');
  const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
  const date=value=>value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',dateStyle:'short',timeStyle:'short'}).format(new Date(value)):'从未登录';
  let pending;
  function render(data,params) {
    const body=q('#manager-rows');body.replaceChildren();
    for(const user of data.users) {
      const row=el('tr'),name=el('td'),identity=el('td'),when=el('td'),action=el('td');
      name.append(el('b',user.username),el('small','ID '+user.id));
      identity.append(el('span',user.real_name||'未填写'),el('small',user.student_number||'未填写学号'));
      when.append(el('small',date(user.date_joined)),el('small',date(user.last_login)));
      const link=el('a','查看 / 管理','text-link');link.href=root.dataset.detailPrefix+user.id+'/';action.append(link);
      row.append(name,identity,el('td',user.role_label),el('td',user.status_label),when,action);body.append(row);
    }
    if(!data.users.length){const td=el('td','没有匹配账号。');td.colSpan=6;const row=el('tr');row.append(td);body.append(row);}
    for(const key of ['total','active','archived','admins'])q('#manager-count-'+key).textContent=data.counts[key];
    const page=data.pagination;
    q('#manager-summary').textContent=`共${page.total}个匹配账号 · 时间为北京时间`;
    const nav=q('#manager-pagination');nav.replaceChildren();
    for(const [label,num] of [['上一页',page.page-1],['下一页',page.page+1]]) {
      if(label==='下一页')nav.append(el('span',`第${page.page} / ${page.pages}页`));
      if(num<1||num>page.pages)continue;
      const query=new URLSearchParams(params);query.set('page',String(num));
      const link=el('a',label,'button secondary');link.href='?'+query;link.addEventListener('click',event=>{event.preventDefault();load(query);});nav.append(link);
    }
    q('#manager-export').href=root.dataset.export+'?'+params;
  }
  async function load(params) {
    pending?.abort();const controller=new AbortController();pending=controller;
    q('#manager-error').textContent='正在读取用户…';
    try {
      const response=await fetch(root.dataset.api+'?'+params,{signal:controller.signal,cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(response.status===401?'登录已过期，请重新登录。':response.status===403?'需要开发者管理员权限。':'查询失败，请检查筛选条件或网络。');
      const data=await response.json();params.set('page',String(data.pagination.page));
      render(data,params);history.replaceState(null,'','?'+params);q('#manager-error').textContent='';
    } catch(error){if(error.name!=='AbortError')q('#manager-error').textContent=error.message;}
  }
  const initial=q('#manager-initial');
  if(initial)render(JSON.parse(initial.textContent),new URLSearchParams(location.search));
  form.addEventListener('submit',event=>{event.preventDefault();const params=new URLSearchParams(new FormData(form));params.set('page','1');load(params);});
})();
