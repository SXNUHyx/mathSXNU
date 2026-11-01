/* Local assets only. Student text is always rendered through textContent. */
(() => {
  const note = document.querySelector('#note');
  if (note) {
    const update = () => { document.querySelector('#char-count').textContent = `${note.value.length} / 300`; };
    note.addEventListener('input', update);
    update();
  }
  const copy = document.querySelector('#copy-link');
  if (copy) copy.addEventListener('click', async () => {
    const input = document.querySelector('#student-link');
    try {
      await navigator.clipboard.writeText(input.value);
      copy.textContent = '链接已复制 ✓';
    } catch (_) {
      input.focus(); input.select();
      copy.textContent = '已选中链接，请长按或按 Ctrl+C 复制';
    }
  });
  const dashboard = document.querySelector('#dashboard');
  if (!dashboard) return;
  const colors = {green: '#3b9375', yellow: '#dfa943', red: '#d87467'};
  function render(data) {
    document.querySelector('#total').textContent = data.total;
    let angle = 0;
    const gradient = [];
    for (const row of data.rows) {
      document.querySelector(`#count-${row.value}`).textContent = row.count;
      document.querySelector(`#percent-${row.value}`).textContent = row.percent;
      document.querySelector(`#bar-${row.value}`).style.width = `${row.percent}%`;
      const end = angle + (data.total ? row.count / data.total * 360 : 0);
      gradient.push(`${colors[row.value]} ${angle}deg ${end}deg`);
      angle = end;
    }
    const donut = document.querySelector('#donut');
    donut.style.background = data.total ? `conic-gradient(${gradient.join(',')})` : '#e9ede9';
    donut.setAttribute('aria-label', `当前${data.total}份反馈，${data.rows.map(r => `${r.label}${r.count}份，占${r.percent}%`).join('；')}`);
    const yellow = data.rows.find(r => r.value === 'yellow').count;
    const red = data.rows.find(r => r.value === 'red').count;
    document.querySelector('#chart-insight').textContent = !data.total
      ? '等待同学们发出第一个信号。'
      : red ? `有 ${red} 份反馈表示需要帮助。可以暂停一下，看看具体的困惑。`
      : yellow ? `有 ${yellow} 份反馈表示仍有疑惑。可以补充一个例子，再确认理解。`
      : '目前收到的反馈均为“听懂了”。也可以用一个问题再确认理解。';
    document.querySelector('#updated').textContent = data.updated;
    document.querySelector('#participation').textContent = data.expected_count
      ? `预计 ${data.expected_count} 人 · 当前反馈 / 预计人数 ${data.participation}%（供参考）`
      : '未设置预计人数 · 按账号最新状态统计';
    document.querySelector('#data-scope').textContent = `当前含 ${data.account_count} 份账号反馈、${data.legacy_count} 份历史不记名反馈。账号反馈按每个账号一份当前状态统计；历史记录无法自动归属新账号，混合数据不代表严格人数。看板和CSV不展示用户名。`;
    const live = document.querySelector('#live-status');
    live.textContent = data.is_open ? '接收中 · 每5秒更新' : '已结束';
    live.classList.toggle('open', data.is_open);
    const notes = document.querySelector('#notes');
    notes.replaceChildren();
    if (!data.notes.length) {
      const empty = document.createElement('p'); empty.className = 'empty muted';
      empty.textContent = '还没有补充说明。学生可以只选择信号，不必填写文字。'; notes.append(empty);
    }
    for (const item of data.notes) {
      const article = document.createElement('article'); article.className = 'feedback-note';
      const heading = document.createElement('div'); heading.className = 'spread';
      const label = document.createElement('span'); label.className = `status-text ${item.status}`; label.textContent = item.label;
      const time = document.createElement('time'); time.textContent = item.time;
      const text = document.createElement('p'); text.textContent = item.text;
      heading.append(label, time); article.append(heading, text); notes.append(article);
    }
  }
  render(JSON.parse(document.querySelector('#initial-stats').textContent));
  async function refresh() {
    if (!document.hidden) {
      try {
        const response = await fetch(dashboard.dataset.statsUrl, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
        if (!response.ok || response.redirected) throw new Error('unavailable');
        render(await response.json());
        document.querySelector('#connection-error').hidden = true;
      } catch (_) {
        const error = document.querySelector('#connection-error');
        error.textContent = '更新暂时中断，以上为上次成功获取的数据。请检查网络或重新登录。'; error.hidden = false;
        document.querySelector('#live-status').textContent = '连接中断 · 数据可能过时';
      }
    }
    window.setTimeout(refresh, 5000);
  }
  window.setTimeout(refresh, 5000);
})();
