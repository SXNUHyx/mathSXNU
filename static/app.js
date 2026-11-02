/* All student/teacher input is inserted as text. KaTeX runs with trust:false. */
(() => {
  const q = (s, root = document) => root.querySelector(s);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  function math(root = document) {
    if (!window.renderMathInElement) return;
    const nodes = root.matches?.('.math-content') ? [root] : root.querySelectorAll('.math-content');
    for (const node of nodes) {
      if (node.dataset.mathRendered) continue;
      renderMathInElement(node, {trust: false, throwOnError: false, strict: 'warn', delimiters: [
        {left: '$$', right: '$$', display: true}, {left: '\\[', right: '\\]', display: true},
        {left: '\\(', right: '\\)', display: false}, {left: '$', right: '$', display: false}
      ]});
      node.dataset.mathRendered = '1';
    }
  }
  math();
  q('#print-report')?.addEventListener('click', async e => {
    const button = e.currentTarget; button.disabled = true;
    try {
      const images = [...document.querySelectorAll('.report img')];
      images.forEach(img => { img.loading = 'eager'; });
      await Promise.race([Promise.all(images.map(img => img.decode().catch(() => {}))), new Promise(resolve => setTimeout(resolve, 10000))]);
      await document.fonts.ready; window.print();
    } finally { button.disabled = false; }
  });
  q('#ai-question-form')?.addEventListener('submit', () => { q('#ai-send').disabled = true; q('#ai-progress').textContent = '正在处理问题，请稍候。外部模型连接最多等待约20秒。'; });
  function files(items, parent) {
    const box = el('div', 'question-files');
    for (const item of items || []) {
      const link = el('a', 'question-file'); link.href = item.url; link.target = '_blank'; link.rel = 'noopener';
      if (item.image) { const img = el('img'); img.src = item.url; img.alt = item.name; img.loading = 'lazy'; link.append(img); }
      link.append(el('span', '', item.name + ' ↓')); box.append(link);
    }
    parent.append(box);
  }
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', e => { if (!window.confirm(form.dataset.confirm)) e.preventDefault(); }));
  document.querySelectorAll('textarea.latex-editor').forEach(editor => {
    const preview = el('div', 'math-content math-preview');
    preview.setAttribute('aria-label', '公式预览');
    const update = () => { preview.textContent = editor.value || '公式和文字预览将显示在这里'; delete preview.dataset.mathRendered; math(preview); };
    editor.after(preview); editor.addEventListener('input', update); update();
  });
  const note = q('#note');
  if (note) { const update = () => { q('#char-count').textContent = `${note.value.length} / ${note.maxLength}`; }; note.addEventListener('input', update); update(); }
  const copy = q('#copy-link');
  if (copy) copy.addEventListener('click', async () => { const input = q('#student-link'); try { await navigator.clipboard.writeText(input.value); copy.textContent = '链接已复制 ✓'; } catch (_) { input.focus(); input.select(); copy.textContent = '已选中链接，请长按或按 Ctrl+C 复制'; } });
  async function json(url, options = {}) {
    const response = await fetch(url, {cache: 'no-store', ...options, headers: {'Accept': 'application/json', ...(options.headers || {})}});
    if (!response.ok || response.redirected) throw new Error(String(response.status));
    return response.json();
  }
  function poll(task, milliseconds) { async function run() { if (!document.hidden) await task(); window.setTimeout(run, milliseconds); } window.setTimeout(run, milliseconds); }
  const dashboard = q('#dashboard');
  if (dashboard) {
    const colors = {green: '#3b9375', yellow: '#dfa943', red: '#d87467'};
    let feedbackSignature = '', insightSignature = '';
    function render(data) {
      const insightKey = JSON.stringify(data.insights);
      if (data.insights && insightKey !== insightSignature) {
        insightSignature = insightKey;
        const box = q('#keyword-insights'), info = data.insights;
        box.replaceChildren(el('h2', '', '同学们主要疑惑在哪里？'), el('p', 'muted small', `最新黄/红反馈：${info.students}位疑问学生，${info.text_questions}份文字说明。每个词每人只计一次，不分析附件；每5秒更新。`));
        const grid = el('div', 'keyword-grid');
        for (const term of info.terms) {
          const card = el('article', 'keyword-card'), details = el('details');
          card.append(el('b', '', term.term), el('span', '', `${term.count}人 · ${term.percent}%`));
          details.append(el('summary', '', '查看问题片段'));
          term.examples.forEach(text => details.append(el('p', '', text))); card.append(details); grid.append(card);
        }
        if (!info.terms.length) grid.append(el('p', 'muted', '暂无可统计的疑问文字。'));
        box.append(grid, el('h3', '', '相关模块'));
        info.modules.forEach(module => box.append(el('p', 'small', `${module.title}：${module.count}人`)));
        box.append(el('p', 'muted small', '百分比以疑问学生数为分母；中文分词只供定位问题，不代表知识点掌握率。'));
      }
      q('#total').textContent = data.total;
      let angle = 0; const gradient = [];
      for (const row of data.rows) {
        q(`#count-${row.value}`).textContent = row.count; q(`#percent-${row.value}`).textContent = row.percent;
        q(`#bar-${row.value}`).style.width = `${row.percent}%`;
        const end = angle + (data.total ? row.count / data.total * 360 : 0); gradient.push(`${colors[row.value]} ${angle}deg ${end}deg`); angle = end;
      }
      q('#donut').style.background = data.total ? `conic-gradient(${gradient.join(',')})` : '#e9ede9';
      q('#donut').setAttribute('aria-label', `当前${data.total}份反馈，${data.rows.map(r => `${r.label}${r.count}份，占${r.percent}%`).join('；')}`);
      const yellow = data.rows.find(r => r.value === 'yellow').count, red = data.rows.find(r => r.value === 'red').count;
      q('#chart-insight').textContent = !data.total ? '等待同学们发出第一个信号。' : red ? `有 ${red} 份反馈表示需要帮助，可以在下方查看学生姓名、学号和问题。` : yellow ? `有 ${yellow} 份反馈表示仍有疑惑，可以补充解释。` : '目前反馈均为“听懂了”，也可以用一个问题再确认理解。';
      q('#updated').textContent = data.updated;
      q('#participation').textContent = data.expected_count ? `预计 ${data.expected_count} 人 · 反馈 / 预计人数 ${data.participation}%（供参考）` : '未设置预计人数 · 按账号最新状态统计';
      q('#data-scope').textContent = `含 ${data.account_count} 份账号反馈、${data.legacy_count} 份历史不记名反馈。姓名学号由学生填写，未经学校核验；导出包含身份信息，请妥善保管。`;
      const live = q('#live-status'); live.textContent = data.is_open ? '接收中 · 每5秒更新' : '已结束'; live.classList.toggle('open', data.is_open);
      q('#feedback-page').textContent = `第 ${data.page} / ${data.pages} 页`;
      q('#feedback-prev').hidden = data.page <= 1; q('#feedback-prev').href = `?feedback_page=${data.page - 1}#feedback`;
      q('#feedback-next').hidden = data.page >= data.pages; q('#feedback-next').href = `?feedback_page=${data.page + 1}#feedback`;
      const signature = JSON.stringify(data.notes);
      if (signature === feedbackSignature) return;
      feedbackSignature = signature;
      const notes = q('#notes'); notes.replaceChildren();
      if (!data.notes.length) notes.append(el('p', 'empty muted', '还没有收到学生反馈。'));
      for (const item of data.notes) {
        const article = el('article', 'feedback-note'), heading = el('div', 'spread');
        heading.append(el('span', `status-text ${item.status}`, item.label), el('time', '', item.time));
        article.append(heading, el('h3', '', `${item.student_name} · 学号 ${item.student_number}`), el('p', 'math-content', item.text || '学生未填写补充说明'));
        files(item.attachments, article);
        for (const reply of item.replies) {
          const box = el('div', 'teacher-explanation'); box.append(el('span', 'muted small', `已回复 · ${reply.time} · ${reply.unread ? '学生未读' : '学生已读'}`), el('p', 'math-content', reply.message)); article.append(box);
        }
        if (item.can_reply) { const link = el('a', 'button secondary', '回复这位学生 →'); link.href = item.reply_url; article.append(link); const history = el('a', 'text-link', '查看提问与附件历史'); history.href = item.reply_url + '#question-history'; article.append(history); }
        else article.append(el('p', 'muted small', '历史不记名记录无法定向回复。'));
        notes.append(article);
      }
      math(notes);
    }
    render(JSON.parse(q('#initial-stats').textContent));
    poll(async () => { try { render(await json(dashboard.dataset.statsUrl)); q('#connection-error').hidden = true; } catch (_) { q('#connection-error').hidden = false; q('#connection-error').textContent = '更新中断，以上为上次数据。请检查网络或重新登录。'; q('#live-status').textContent = '连接中断 · 数据可能过时'; } }, 5000);
  }
  const notifications = q('#student-notifications');
  if (notifications) {
    let signature = '';
    const refresh = async () => {
      try {
        const data = await json(notifications.dataset.url), badge = q('#unread-count');
        badge.textContent = data.count; badge.hidden = !data.count;
        const key = JSON.stringify(data.items);
        if (signature === key) return;
        signature = key; notifications.replaceChildren();
        if (data.count) {
          const box = el('div', 'notice'); box.append(el('strong', '', `您有 ${data.count} 条未读教师回复`));
          for (const item of data.items) { const link = el('a', 'notification-link', `${item.title}：${item.preview}`); link.href = item.url; box.append(link); }
          notifications.append(box);
        }
      } catch (_) { signature = ''; if (!notifications.children.length) notifications.append(el('p', 'muted small', '暂时无法检查新回复，正在重试。')); }
    };
    refresh(); poll(refresh, 3000);
  }
  const replies = q('#teacher-replies');
  if (replies) {
    let signature = '';
    const refresh = async () => {
      try {
        const data = await json(replies.dataset.updatesUrl), key = JSON.stringify(data.replies);
        if (key !== signature) {
          signature = key; const list = q('#reply-list'); list.replaceChildren();
          if (!data.replies.length) list.append(el('p', 'muted', '暂时没有老师的回复。'));
          data.replies.forEach(reply => { const article = el('article', 'teacher-explanation'); article.append(el('span', 'muted small', `${reply.time} · ${reply.unread ? '未读' : '已读'}`), el('blockquote', 'math-content', reply.question || '针对您的学习状态')); files(reply.attachments, article); article.append(el('div', 'math-content', reply.message)); list.append(article); });
          q('#read-up-to').value = data.replies.length ? data.replies.at(-1).id : '';
          q('#read-replies-button').disabled = !data.replies.length;
          math(list);
        }
        q('#reply-connection').textContent = data.is_open ? '答疑连接正常 · 约3秒自动检查' : '课堂收集已结束，仍可接收老师回复。';
      } catch (_) { q('#reply-connection').textContent = '答疑更新暂时中断。请检查网络；课堂删除后将无法继续访问。'; }
    };
    q('#read-replies-form').addEventListener('submit', async e => { e.preventDefault(); try { await json(replies.dataset.readUrl, {method: 'POST', body: new FormData(e.currentTarget)}); await refresh(); } catch (_) { q('#reply-connection').textContent = '标记失败，请检查网络后重试。'; } });
    refresh(); poll(refresh, 3000);
  }
})();
