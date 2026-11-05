/* Edges describe recorded module membership and keyword co-occurrence only. */
(() => {
  const root = document.querySelector('#question-graph');
  if (!root) return;
  const $ = s => root.querySelector(s), svg = $('#question-graph-svg');
  const make = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const shape = (tag, attrs, text) => {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k,v] of Object.entries(attrs)) n.setAttribute(k,v);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  let payload = null, signature = '', selection = 'root', nodes = new Map();
  const short = text => [...text].length > 10 ? [...text].slice(0,10).join('')+'…' : text;

  function detail() {
    const node = nodes.get(selection) || nodes.get('root');
    if (!node) return;
    $('#graph-detail-title').textContent = node.title;
    $('#graph-detail-count').textContent = `${node.questions.length}份当前问题 · 未回答 ${node.questions.filter(q => !q.answered).length}份`;
    const list = $('#graph-questions'); list.replaceChildren();
    if (!node.questions.length) list.append(make('p','muted','暂无符合条件的问题。'));
    for (const q of node.questions) {
      const item = make('article','graph-question');
      item.append(make('p',`status-text ${q.status}`,`${q.status === 'yellow' ? '有点疑惑' : '需要帮助'} · ${q.answered ? '已回答' : '未回答'}`));
      item.append(make('h4','',`${q.name} · 学号 ${q.number}`));
      item.append(make('p','',q.text || '仅提交状态或附件，未填写问题文字。'));
      if (q.reply_url) { const link = make('a','text-link','查看问题与回复 →'); link.href=q.reply_url; item.append(link); }
      else item.append(make('p','muted small','历史不记名记录无法定向回复。'));
      list.append(item);
    }
    for (const g of svg.querySelectorAll('[data-node]')) {
      const active = g.dataset.node === selection;
      g.classList.toggle('graph-selected',active); g.setAttribute('aria-pressed',String(active));
    }
  }
  function draw() {
    if (!payload) return;
    const type = $('#graph-status').value, answer = $('#graph-answer').value;
    const filtered = payload.questions.filter(q => (type === 'all' || q.status === type) && (answer === 'all' || (answer === 'answered' ? q.answered : !q.answered)));
    const modules = new Map(), keywords = new Map();
    for (const q of filtered) {
      if (!modules.has(q.module_id)) modules.set(q.module_id,{label:q.module,questions:[]});
      modules.get(q.module_id).questions.push(q);
      for (const term of q.keywords) {
        if (!keywords.has(term)) keywords.set(term,[]);
        keywords.get(term).push(q);
      }
    }
    const moduleList = [...modules].sort((a,b) => b[1].questions.length-a[1].questions.length || a[0].localeCompare(b[0]));
    const topics = [...keywords].sort((a,b) => b[1].length-a[1].length || a[0].localeCompare(b[0])).slice(0,12);
    const shown = moduleList.slice(0,8);
    if (moduleList.length > 8) shown.push(['other',{label:'其他模块',questions:moduleList.slice(8).flatMap(x => x[1].questions)}]);
    svg.replaceChildren(); nodes = new Map();
    nodes.set('root',{title:'全部关联问题',label:payload.title,questions:filtered,x:105,y:280,kind:'lesson'});
    shown.forEach(([id,m],i) => nodes.set('module:'+id,{title:m.label,label:m.label,questions:m.questions,x:360,y:42+(i+.5)*476/Math.max(1,shown.length),kind:'module'}));
    topics.forEach(([term,questions],i) => nodes.set('term:'+term,{title:'关键词：'+term,label:term,questions,x:660,y:24+(i+.5)*512/Math.max(1,topics.length),kind:'term'}));
    if (!nodes.has(selection)) selection='root';
    function edge(from,to,count) {
      const path = shape('path',{d:`M${from.x} ${from.y} C${(from.x+to.x)/2} ${from.y}, ${(from.x+to.x)/2} ${to.y}, ${to.x} ${to.y}`,class:'graph-edge','stroke-width':Math.min(5,1+Math.log2(1+count)),fill:'none'});
      path.append(shape('title',{},`${from.label} → ${to.label}：${count}份问题`)); svg.append(path);
    }
    for (const node of nodes.values()) {
      if (node.kind !== 'module') continue;
      edge(nodes.get('root'),node,node.questions.length);
      for (const [term] of topics) {
        const count = node.questions.filter(q => q.keywords.includes(term)).length;
        if (count) edge(node,nodes.get('term:'+term),count);
      }
    }
    for (const [id,node] of nodes) {
      const g = shape('g',{transform:`translate(${node.x} ${node.y})`,class:'graph-node graph-'+node.kind,tabindex:'0',role:'button','data-node':id,'aria-label':`${node.kind === 'term' ? '关键词：' : node.kind === 'module' ? '模块：' : '课堂：'}${node.label}，${node.questions.length}份问题`});
      g.append(shape('title',{},`${node.title} · ${node.questions.length}份问题`));
      g.append(shape('rect',{x:node.kind === 'term' ? -85 : -96,y:-20,width:node.kind === 'term' ? 170 : 192,height:40,rx:16}));
      g.append(shape('text',{'text-anchor':'middle',y:5},`${short(node.label)} · ${node.questions.length}`));
      const select = () => { selection=id; detail(); };
      g.addEventListener('click',select);
      g.addEventListener('keydown',e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); } });
      svg.append(g);
    }
    $('#graph-scope').textContent = `当前筛选 ${filtered.length}份问题 · 显示 ${topics.length}个高频关键词${payload.total > payload.questions.length ? ` · 图谱取优先未回答的前${payload.limit}份，课堂共有${payload.total}份当前疑惑与求助反馈` : ''}`;
    detail();
  }
  $('#graph-status').addEventListener('change',() => { selection='root'; draw(); });
  $('#graph-answer').addEventListener('change',() => { selection='root'; draw(); });
  $('#graph-reset').addEventListener('click',() => { $('#graph-status').value='all'; $('#graph-answer').value='all'; selection='root'; draw(); });
  function update(next) {
    if (!next) return;
    const key = JSON.stringify(next);
    if (key === signature) return;
    signature=key; payload=next; draw();
  }
  window.addEventListener('mathsig:question-graph',event => update(event.detail));
  const initial = document.querySelector('#initial-stats');
  if (initial) update(JSON.parse(initial.textContent).question_graph);
})();
