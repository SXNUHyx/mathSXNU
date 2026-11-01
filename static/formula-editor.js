/* Local MathLive editor. The optional WIRIS integration is loaded only on request. */
(() => {
  const assets = document.getElementById('formula-editor-assets');
  if (!assets) return;
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, action) => {
    const node = el('button', 'button secondary', text);
    node.type = 'button'; node.addEventListener('click', action); return node;
  };
  const palettes = [
    ['常用', [['分式', String.raw`\frac{a}{b}`], ['平方根', String.raw`\sqrt{x}`], ['幂', 'x^{n}'], ['下标', 'a_{n}'], ['绝对值', String.raw`\left|x\right|`], ['不等式', String.raw`a\le b`], ['希腊字母', String.raw`\alpha+\beta`]]],
    ['微积分', [['定积分', String.raw`\int_a^b f(x)\,dx`], ['二重积分', String.raw`\iint_D f(x,y)\,dx\,dy`], ['极限', String.raw`\lim_{x\to 0} f(x)`], ['导数', String.raw`\frac{df}{dx}`], ['偏导数', String.raw`\frac{\partial f}{\partial x}`], ['级数', String.raw`\sum_{n=1}^{\infty} a_n`]]],
    ['矩阵与方程', [['二阶矩阵', String.raw`\begin{pmatrix}a&b\\c&d\end{pmatrix}`], ['行列式', String.raw`\begin{vmatrix}a&b\\c&d\end{vmatrix}`], ['分段函数', String.raw`f(x)=\begin{cases}x^2&x\ge 0\\-x&x<0\end{cases}`], ['方程组', String.raw`\begin{cases}x+y=1\\x-y=0\end{cases}`], ['向量', String.raw`\vec{a}`]]],
    ['概率统计', [['组合数', String.raw`\binom{n}{k}`], ['期望', String.raw`E(X)=\sum_i x_i p_i`], ['方差', String.raw`\operatorname{Var}(X)=E(X^2)-[E(X)]^2`], ['正态密度', String.raw`f(x)=\frac{1}{\sqrt{2\pi}\sigma}e^{-\frac{(x-\mu)^2}{2\sigma^2}}`], ['样本均值', String.raw`\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i`], ['条件概率', String.raw`P(A\mid B)=\frac{P(A\cap B)}{P(B)}`]]]
  ];
  if (window.MathfieldElement) {
    MathfieldElement.fontsDirectory = assets.dataset.fonts;
    MathfieldElement.soundsDirectory = null;
    MathfieldElement.locale = 'zh-cn';
  }

  // Recognise existing formulas so opening the editor replaces the whole formula.
  function selectedFormula(editor) {
    let start = editor.selectionStart, end = editor.selectionEnd;
    const pattern = /\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|(?<!\\)\$([^$\n]+?)(?<!\\)\$/g;
    for (const match of editor.value.matchAll(pattern)) {
      if (start >= match.index && end <= match.index + match[0].length) {
        return {start: match.index, end: match.index + match[0].length,
          latex: match[1] ?? match[2] ?? match[3] ?? match[4], display: match[2] !== undefined || match[3] !== undefined};
      }
    }
    return {start, end, latex: editor.value.slice(start, end), display: false};
  }

  let wirisScript;
  function loadMathType() {
    if (!wirisScript) wirisScript = new Promise((resolve, reject) => {
      const script = document.createElement('script'); script.src = assets.dataset.mathtypeScript;
      script.onload = resolve;
      script.onerror = () => { wirisScript = null; script.remove(); reject(new Error('MathType资源加载失败')); };
      document.head.append(script);
    });
    return wirisScript;
  }

  document.querySelectorAll('textarea.latex-editor').forEach((editor, index) => {
    const details = el('details', 'formula-panel');
    details.append(el('summary', '', '打开可视化公式编辑器'));
    details.append(el('p', 'muted small', '点击模板后修改公式，也可打开公式键盘。修改已有公式：把光标放进正文中的公式，再打开编辑器。'));
    const mf = el('math-field', 'visual-mathfield');
    mf.setAttribute('aria-label', '可视化公式');
    mf.setAttribute('math-virtual-keyboard-policy', 'manual');
    const source = el('textarea', 'formula-source');
    source.rows = 2; source.id = `formula-source-${index}`;
    source.setAttribute('aria-label', '公式LaTeX（可选）');
    const sourceDetails = el('details', 'formula-source-wrap'); sourceDetails.append(el('summary', '', '查看或粘贴 LaTeX'), source);
    const palette = el('div', 'formula-palette');
    const category = el('select', 'formula-category'); category.setAttribute('aria-label', '公式模板分类');
    for (const [label] of palettes) { const option = el('option', '', label); category.append(option); }
    function renderPalette() {
      palette.replaceChildren();
      for (const [label, value] of palettes[category.selectedIndex][1]) {
        const item = button(label, () => {
          if (!window.MathfieldElement) { source.value += value; return; }
          mf.insert(value); mf.focus(); source.value = mf.value;
        });
        item.addEventListener('mousedown', event => event.preventDefault()); palette.append(item);
      }
    }
    category.addEventListener('change', renderPalette); renderPalette();
    const keyboard = button('打开 / 收起公式键盘', () => {
      if (!window.mathVirtualKeyboard) return;
      mf.focus(); mathVirtualKeyboard.visible ? mathVirtualKeyboard.hide() : mathVirtualKeyboard.show();
    });
    const displayLabel = el('label', 'formula-display');
    const display = document.createElement('input'); display.type = 'checkbox';
    displayLabel.append(display, document.createTextNode('独立一行显示'));
    const status = el('p', 'small formula-status'); status.setAttribute('role', 'status');
    let selection, snapshot;
    const insert = button('插入到正文', () => {
      if (editor.value !== snapshot) { status.textContent = '正文已有变化，请收起并重新打开编辑器，重新选择插入位置。'; return; }
      const latex = (window.MathfieldElement ? mf.value : source.value).trim();
      if (!latex) { status.textContent = '请先输入公式。'; return; }
      const value = display.checked ? `\\[${latex}\\]` : `\\(${latex}\\)`;
      if (editor.maxLength > 0 && editor.value.length - (selection.end - selection.start) + value.length > editor.maxLength) {
        status.textContent = '插入后超过正文长度上限，请先缩短内容。'; return;
      }
      editor.setRangeText(value, selection.start, selection.end, 'end');
      editor.dispatchEvent(new Event('input', {bubbles: true})); details.open = false; editor.focus();
    });
    insert.className = 'button primary';
    const actions = el('div', 'content-actions'); actions.append(keyboard, displayLabel, insert);
    details.append(category, palette, mf, sourceDetails, actions, status);
    editor.before(details);
    mf.addEventListener('input', () => { source.value = mf.value; });
    source.addEventListener('input', () => { if (window.MathfieldElement) mf.value = source.value; });
    details.addEventListener('toggle', () => {
      if (!details.open) { window.mathVirtualKeyboard?.hide(); return; }
      selection = selectedFormula(editor); snapshot = editor.value;
      source.value = selection.latex; display.checked = selection.display; status.textContent = '';
      insert.textContent = selection.end > selection.start ? '替换选中的公式 / 文字' : '插入到正文';
      if (window.MathfieldElement) { mf.value = selection.latex; mf.focus(); }
      else { mf.hidden = true; keyboard.hidden = true; sourceDetails.open = true; status.textContent = '可视化组件未加载，请在此输入LaTeX，仍可插入与预览。'; }
    });

    if (assets.dataset.mathtypeUri) {
      let integration;
      const info = el('p', 'muted small', 'MathType 使用学校配置的授权服务；公式会发送到该服务处理。');
      const message = el('p', 'small'); message.setAttribute('role', 'status');
      const open = button('使用 MathType（学校授权）', async () => {
        open.disabled = true; message.textContent = '正在连接学校的MathType服务…';
        try {
          await loadMathType();
          if (!integration) {
            // The official Core supports textarea targets and writes $$LaTeX$$.
            // Avoid GenericIntegration's HTML parsing: content remains plain text.
            class TextareaIntegration extends WirisPlugin.GenericIntegration {
              callbackFunction() {
                WirisPlugin.IntegrationModel.prototype.callbackFunction.call(this);
                this.listeners.fire('onTargetReady', {});
                this.ready = true;
                this.core.addListener(WirisPlugin.Listeners.newListener('onAfterFormulaInsertion', () => {
                  // WIRIS fires before updating the target. Refresh after insertion.
                  window.setTimeout(() => editor.dispatchEvent(new Event('input', {bubbles: true})), 0);
                }));
              }
            }
            integration = new TextareaIntegration({target: editor, toolbar: el('div'),
              serviceProviderProperties: {URI: assets.dataset.mathtypeUri, server: assets.dataset.mathtypeServer},
              integrationParameters: {editorParameters: {language: 'zh'}}});
            integration.init();
          }
          if (!integration.ready) throw new Error('服务未就绪');
          details.open = false; WirisPlugin.currentInstance = integration;
          integration.openNewFormulaEditor(); message.textContent = '';
        } catch (_) {
          integration = null;
          message.textContent = 'MathType连接失败，请检查学校授权、服务地址及网络。可继续使用上方免费的可视化编辑器。';
        } finally { open.disabled = false; }
      });
      editor.before(open, info, message);
    }
  });
})();
