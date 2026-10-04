'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const icon = (name) => '<svg aria-hidden="true"><use href="#i-' + name + '"/></svg>';
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const uid = () => crypto.randomUUID ? crypto.randomUUID() : Date.now() + '-' + Math.random();
  const formatSize = (size) => size < 1024 ? size + ' B' : size < 1048576 ? (size / 1024).toFixed(1) + ' KB' : (size / 1048576).toFixed(1) + ' MB';
  const state = { chats: [], current: null, pending: [], busy: false, token: 0, drawer: 'files', selectedFile: null };
  const sampleRows = [
    ['指标', '2023', '2024', '单位'],
    ['营业收入', '372037280000', '407149600000', '人民币元'],
    ['归母净利润', '33719935000', '38537237000', '人民币元'],
    ['经营现金流净额', '57902611000', '60511572000', '人民币元']
  ];
  const sampleText = sampleRows.map(r => r.join(',')).join('\n');
  let toastTimer;
  function toast(text) {
    $('toast').textContent = text;
    $('toast').classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 3200);
  }
  function showMenu(id, trigger, show) {
    const visible = show === undefined ? $(id).classList.contains('hidden') : show;
    $(id).classList.toggle('hidden', !visible);
    $(trigger).setAttribute('aria-expanded', String(visible));
  }
  function closeMenus() {
    showMenu('attachMenu', 'attachButton', false);
    showMenu('modelMenu', 'modelButton', false);
  }
  function updateComposer() {
    $('messageInput').style.height = 'auto';
    $('messageInput').style.height = Math.min($('messageInput').scrollHeight, 168) + 'px';
    $('sendButton').disabled = !state.busy && !$('messageInput').value.trim() && !state.pending.length;
    $('sendButton').innerHTML = state.busy ? '<span class="stop-square"></span>' : icon('up');
    $('sendButton').setAttribute('aria-label', state.busy ? '停止生成' : '发送消息');
    $('sendButton').title = state.busy ? '停止生成' : '发送消息';
    $('composerContext').textContent = state.pending.length ? state.pending.length + ' 个附件 · 仅本地预览' : '当前项目';
  }
  function visibleFiles() {
    const files = state.chats.flatMap(c => c.messages.flatMap(m => m.files || []));
    return [...new Map([...files, ...state.pending].map(f => [f.id, f])).values()];
  }
  function fileChip(file, removable) {
    const chip = el('div', 'file-chip');
    const main = el('button', 'file-chip-main');
    main.type = 'button';
    main.innerHTML = icon(file.kind === 'pdf' ? 'file' : 'table');
    const words = el('span', 'file-chip-text');
    words.append(el('b', '', file.name), el('small', '', file.status));
    main.append(words);
    main.onclick = () => { state.selectedFile = file; openDrawer('files'); };
    chip.append(main);
    if (removable) {
      const remove = el('button', 'icon-btn remove-file');
      remove.innerHTML = icon('x');
      remove.setAttribute('aria-label', '移除附件 ' + file.name);
      remove.onclick = () => {
        state.pending = state.pending.filter(f => f.id !== file.id);
        if (state.selectedFile?.id === file.id) state.selectedFile = null;
        renderAttachments();
      };
      chip.append(remove);
    }
    return chip;
  }
  function renderAttachments() {
    $('attachments').replaceChildren(...state.pending.map(f => fileChip(f, true)));
    $('libraryCount').textContent = visibleFiles().length;
    if (!$('fileDrawer').classList.contains('hidden')) renderDrawer();
    updateComposer();
  }
  function parseDelimited(text, separator) {
    text = text.replace(/^\uFEFF/, '');
    const rows = [];
    let row = [], cell = '', quoted = false, atStart = true;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === '"') {
        if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
        else if (quoted) quoted = false;
        else if (atStart) quoted = true;
        else cell += c;
      } else if (!quoted && (c === separator || c === '\n' || c === '\r')) {
        row.push(cell); cell = ''; atStart = true;
        if (c !== separator) {
          if (c === '\r' && text[i + 1] === '\n') i++;
          if (row.some(v => v.trim())) rows.push(row);
          row = [];
        }
      } else { cell += c; atStart = false; }
    }
    if (quoted) throw new Error('存在未闭合的引号');
    row.push(cell);
    if (row.some(v => v.trim())) rows.push(row);
    if (!rows.length) throw new Error('文件中没有可预览的内容');
    return rows;
  }
  async function addFiles(files, isSample = false) {
    closeMenus();
    const targetChat = state.current;
    const nextFiles = [];
    for (const file of files) {
      if (state.pending.length + nextFiles.length >= 8) { toast('单条消息最多添加 8 个附件'); break; }
      const kind = file.name.split('.').pop().toLowerCase();
      if (!['xlsx', 'xls', 'csv', 'tsv', 'pdf'].includes(kind)) { toast('支持 Excel、CSV、TSV 和 PDF'); continue; }
      if (file.size > 25 * 1048576) { toast('原型单个附件上限为 25 MB'); continue; }
      if ([...state.pending, ...nextFiles].some(f => f.name === file.name && f.size === file.size)) continue;
      const record = { id: uid(), name: file.name, kind, size: file.size, sample: isSample, rows: null, status: '已添加 · 待后端解析' };
      if (kind === 'csv' || kind === 'tsv') {
        if (file.size > 2 * 1048576) record.status = '已添加 · 超过本地预览范围';
        else {
          try {
            record.rows = parseDelimited(await file.text(), kind === 'tsv' ? '\t' : ',');
            const width = Math.max(...record.rows.slice(0, 1000).map(r => r.length));
            record.status = '本地预览 · ' + Math.max(0, record.rows.length - 1) + ' 行 / ' + width + ' 列';
          } catch (e) { record.status = '预览失败 · 待后端解析'; record.error = e.message; }
        }
      }
      nextFiles.push(record);
    }
    // Reading a local file is asynchronous; never attach it to a different conversation.
    if (state.current !== targetChat) { toast('对话已切换，请在当前对话重新添加附件'); return; }
    state.pending.push(...nextFiles);
    renderAttachments();
    $('messageInput').focus();
  }
  function makeTable(rows, limit = 6) {
    const wrap = el('div', 'table-scroll'), table = el('table'), head = el('thead'), body = el('tbody');
    const tr = el('tr');
    rows[0].slice(0, 10).forEach(v => tr.append(el('th', '', v)));
    head.append(tr);
    rows.slice(1, limit + 1).forEach(row => {
      const r = el('tr');
      row.slice(0, 10).forEach(v => r.append(el('td', 'numeric', v)));
      body.append(r);
    });
    table.append(head, body); wrap.append(table);
    return wrap;
  }
  function renderChatList() {
    $('chatList').replaceChildren();
    const sample = el('button', 'chat-item' + (state.current?.example ? ' active' : ''));
    sample.append(el('span', 'chat-title', '美的年报比较'), el('span', 'small-badge', '示例'));
    sample.onclick = openExample;
    $('chatList').append(sample);
    [...state.chats].reverse().filter(c => !c.example && c.messages.length).forEach(chat => {
      const button = el('button', 'chat-item' + (chat === state.current ? ' active' : ''));
      button.append(el('span', 'chat-title', chat.title));
      button.onclick = () => switchChat(chat);
      $('chatList').append(button);
    });
  }
  function stopRun() {
    if (!state.busy) return;
    state.token++;
    state.busy = false;
    const message = state.current.messages[state.current.messages.length - 1];
    if (message?.kind === 'progress') { message.kind = 'stopped'; }
    renderConversation();
  }
  function switchChat(chat) {
    stopRun();
    if (state.current) state.current.draft = { text: $('messageInput').value, files: [...state.pending] };
    state.current = chat;
    state.pending = [...(chat.draft?.files || [])];
    $('messageInput').value = chat.draft?.text || '';
    $('app').classList.remove('mobile-sidebar');
    closeDrawer(); closeMenus();
    renderConversation(); renderAttachments(); renderChatList();
    requestAnimationFrame(() => $('messageInput').focus());
  }
  function newChat() {
    const chat = { id: uid(), title: '新对话', messages: [], draft: null };
    state.chats.push(chat);
    switchChat(chat);
  }
  function openExample() {
    let chat = state.chats.find(c => c.example);
    if (!chat) {
      const sample = { id: uid(), name: '美的集团_2023-2024_示例.csv', kind: 'csv', size: new Blob([sampleText]).size, sample: true, rows: sampleRows, status: '示例表 · 3 行 / 4 列' };
      chat = { id: uid(), example: true, title: '美的年报比较', messages: [
        { role: 'user', text: '比较美的集团2024年和2023年的收入、归母净利润与现金流，列出同比变化，并给出原文依据。', files: [sample] },
        { role: 'assistant', kind: 'sample' }
      ] };
      state.chats.push(chat);
    }
    switchChat(chat);
    $('conversationScroll').scrollTop = 0;
  }
  function sampleAnswer() {
    const body = el('div', 'answer-body');
    body.append(el('p', '', '2024年，美的集团的收入、归母净利润与经营现金流均高于2023年。归母净利润增幅最大，为14.29%。'));
    body.append(makeTable([
      ['指标', '2023年', '2024年', '同比'],
      ['营业收入', '3,720.37', '4,071.50', '+9.44%'],
      ['归母净利润', '337.20', '385.37', '+14.29%'],
      ['经营现金流净额', '579.03', '605.12', '+4.51%']
    ]));
    const note = el('p', 'unit-note', '单位：亿元人民币 · 合并口径 · 中国会计准则');
    const cite = el('button', 'source-pill');
    cite.innerHTML = icon('file') + '年报第 9 页';
    cite.onclick = () => openDrawer('evidence');
    note.append(cite); body.append(note);
    body.append(el('h3', '', '营业收入对比'));
    [['2023', 3720.3728], ['2024', 4071.496]].forEach(([year, value], i) => {
      const line = el('div', 'preview-chart');
      const bg = el('div', 'bar-bg'), bar = el('div', 'bar' + (i ? ' last' : ''));
      bar.style.width = (value / 4500 * 100) + '%'; bg.append(bar);
      line.append(el('span', '', year), bg, el('span', 'amount', value.toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 2 })));
      body.append(line);
    });
    body.append(el('p', 'chart-scale', '比例尺从 0 起 · 统一上限 4,500 亿元'));
    body.append(el('p', 'citation-note', '同比 =（本年 ÷ 上年 − 1）× 100%。由原始数值计算后四舍五入；此处为预置示例，未调用模型。'));
    const trace = el('details', 'trace');
    trace.append(el('summary', '', '查看正式版的处理路径'));
    const list = el('ol');
    ['附件交由文档服务解析，保存表格与原文位置。', '校验期间、币种、单位与会计口径，写入项目数据库。', 'Agent 调用查询与计算工具；需要自定义制图时运行隔离容器。', '返回结论、数据、图表和可点击的证据。'].forEach(t => list.append(el('li', '', t)));
    trace.append(list); body.append(trace);
    return body;
  }
  function genericAnswer(message) {
    const body = el('div', 'answer-body');
    if (message.files?.length) {
      body.append(el('p', '', '附件已添加到这段对话。下面是本地预览，文件尚未上传、入库或发送给模型。'));
      message.files.forEach(file => {
        body.append(el('h3', '', file.name));
        if (file.rows) {
          body.append(makeTable(file.rows, 5));
          body.append(el('p', 'unit-note', '预览前 ' + Math.min(file.rows.length - 1, 5) + ' 行，最多 10 列；第一行暂作字段名。'));
        } else body.append(el('p', 'unit-note', file.error ? '无法本地预览：' + file.error : '已保留附件信息；Excel 工作表或 PDF 内容需要接入后端解析服务。'));
      });
      body.append(el('p', '', '正式版中，你可以直接在这里发附件并说明分析任务。后端解析并保存数据后，Agent 查询所需字段、计算和制图，结果仍回到当前对话。'));
    } else {
      body.append(el('p', '', '这条消息已记录。当前是对话界面的交互原型，尚未连接主模型，暂不能生成真实分析。'));
      body.append(el('p', '', '可以在输入框旁的“＋”添加表格，或打开左侧“美的年报比较”体验结果、图表与原文引用。模型连接入口在左下角和右上角的“API 配置”。'));
    }
    return body;
  }
  function renderConversation() {
    const chat = state.current;
    const empty = !chat || !chat.messages.length;
    $('chatArea').classList.toggle('empty', empty);
    $('welcome').classList.toggle('hidden', !empty);
    $('messages').classList.toggle('hidden', empty);
    $('quickActions').classList.toggle('hidden', !empty);
    $('messages').replaceChildren();
    (chat?.messages || []).forEach(message => {
      const article = el('article', 'message ' + message.role);
      if (message.role === 'user') {
        if (message.files?.length) {
          const group = el('div', 'user-files');
          message.files.forEach(f => group.append(fileChip(f, false)));
          article.append(group);
        }
        if (message.text) article.append(el('div', 'user-bubble', message.text));
      } else {
        const header = el('div', 'assistant-header');
        header.innerHTML = icon('chat');
        header.append(el('span', '', message.kind === 'sample' ? '金融研究 · 预置示例' : '金融研究 · 交互演示'));
        article.append(header);
        if (message.kind === 'progress') {
          const line = el('div', 'progress-line');
          line.append(el('span', 'progress-dot'), el('span', '', message.stage));
          article.append(line);
        } else if (message.kind === 'stopped') article.append(el('p', 'muted', '已停止本次演示。'));
        else {
          const answer = message.kind === 'sample' ? sampleAnswer() : genericAnswer(message);
          article.append(answer);
          const actions = el('div', 'message-actions'), copy = el('button', 'icon-btn');
          copy.innerHTML = icon('copy'); copy.setAttribute('aria-label', '复制回复');
          copy.onclick = async () => {
            try { await navigator.clipboard.writeText(answer.innerText); toast('回复已复制'); }
            catch { toast('浏览器未允许剪贴板访问，请选择回复文字复制'); }
          };
          const download = el('button', 'icon-btn');
          download.innerHTML = icon('down'); download.setAttribute('aria-label', '下载回复');
          download.onclick = () => {
            const url = URL.createObjectURL(new Blob([answer.innerText], { type: 'text/plain;charset=utf-8' }));
            const link = el('a'); link.href = url; link.download = '金融研究-回复.txt'; link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          };
          actions.append(copy, download, el('span', '', '未调用模型')); article.append(actions);
        }
      }
      $('messages').append(article);
    });
    updateComposer();
  }
  function scrollBottom() {
    requestAnimationFrame(() => { $('conversationScroll').scrollTop = $('conversationScroll').scrollHeight; });
  }
  async function sendMessage() {
    if (state.busy) { stopRun(); return; }
    const text = $('messageInput').value.trim(), files = [...state.pending];
    if (!text && !files.length) return;
    const chat = state.current;
    if (!chat.messages.length) chat.title = (text || files[0].name).slice(0, 24);
    chat.messages.push({ role: 'user', text, files });
    state.pending = []; chat.draft = null;
    $('messageInput').value = '';
    const response = { role: 'assistant', kind: 'progress', stage: '演示：接收消息与附件…', files };
    chat.messages.push(response);
    state.busy = true;
    const token = ++state.token;
    renderConversation(); renderAttachments(); renderChatList(); scrollBottom();
    for (const stage of ['演示：整理文件信息…', '演示：准备显示结果…']) {
      await new Promise(resolve => setTimeout(resolve, 450));
      if (token !== state.token) return;
      response.stage = stage; renderConversation(); scrollBottom();
    }
    await new Promise(resolve => setTimeout(resolve, 450));
    if (token !== state.token) return;
    response.kind = files.length === 1 && files[0].sample ? 'sample' : 'generic';
    state.busy = false;
    renderConversation(); scrollBottom();
  }
  function openDrawer(tab) {
    state.drawer = tab;
    $('fileDrawer').classList.remove('hidden');
    $('app').classList.add('drawer-open');
    $('app').classList.remove('mobile-sidebar');
    renderDrawer();
  }
  function closeDrawer() {
    $('fileDrawer').classList.add('hidden');
    $('app').classList.remove('drawer-open');
  }
  function renderDrawer() {
    document.querySelectorAll('[data-drawer]').forEach(b => b.classList.toggle('active', b.dataset.drawer === state.drawer));
    const target = $('drawerContent');
    target.replaceChildren();
    if (state.drawer === 'evidence') {
      const hasSample = state.current.messages.some(m => m.kind === 'sample');
      if (!hasSample) { target.append(el('div', 'drawer-empty', '当前对话还没有可定位的原文证据。')); return; }
      target.append(el('h3', '', '美的集团 · 2024年年度报告'));
      target.append(el('p', 'muted', 'PDF 第 9 页 / 印刷页码 8 · 主要会计数据'));
      const img = el('img', 'doc-img'); img.src = '../benchmark/review/pages/midea_p9.png'; img.alt = '美的集团2024年年报主要会计数据原页';
      const link = el('a', 'doc-link', '打开完整年报第 9 页 ');
      link.href = '../benchmark/sources/reports/midea_2024.pdf#page=9'; link.target = '_blank'; link.rel = 'noopener';
      link.insertAdjacentHTML('beforeend', icon('external'));
      target.append(img, link, el('p', 'muted', '原表单位为千元，示例显示为亿元；换算时除以 100,000。'));
      return;
    }
    const files = visibleFiles();
    if (!files.length) {
      const empty = el('div', 'drawer-empty');
      empty.innerHTML = icon('folder');
      empty.append(el('p', '', '还没有项目文件。'), el('p', '', '点击对话框旁的“＋”或直接拖入文件。'));
      target.append(empty); return;
    }
    target.append(el('p', 'muted', '本次页面会话中的项目附件 · 刷新后清空'));
    files.forEach(file => {
      const button = el('button', 'drawer-file'); button.innerHTML = icon(file.kind === 'pdf' ? 'file' : 'table');
      const words = el('span');
      words.append(el('b', '', file.name), el('small', '', formatSize(file.size) + ' · ' + file.status));
      button.append(words); button.onclick = () => { state.selectedFile = file; renderDrawer(); };
      target.append(button);
    });
    const file = state.selectedFile && files.find(f => f.id === state.selectedFile.id);
    if (file) {
      const detail = el('div', 'drawer-detail');
      detail.append(el('h3', '', file.name));
      if (file.rows) {
        detail.append(makeTable(file.rows, 5));
        detail.append(el('p', '', '以上是浏览器本地预览，尚未进行财务口径校验或入库。'));
      } else detail.append(el('p', '', '附件已添加。工作表识别、文档解析和 OCR 在正式版后端处理。'));
      target.append(detail);
    }
  }

  // Configuration UI is defined below. No provider requests are made by this prototype.
  const configKey = 'finance-prototype-config-v02';
  const defaults = { llmProvider: 'compatible', llmEndpoint: '', llmModel: '', embeddingEnabled: false, embeddingEndpoint: '', embeddingModel: '', embeddingDimensions: '', ocrMode: 'local', ocrEndpoint: '', ocrModel: '', maxCalls: '24', runTimeout: '120', runBudget: '' };
  let config = { ...defaults };
  const secrets = { llmKey: '', embeddingKey: '', ocrKey: '' };
  try {
    const saved = JSON.parse(localStorage.getItem(configKey) || '{}');
    // Explicit allowlist: never persist credentials, including fields added in the future.
    for (const key of Object.keys(defaults)) {
      if (typeof saved[key] === typeof defaults[key]) config[key] = saved[key];
    }
  } catch { /* Local files may be opened with browser storage disabled. */ }
  let settingsTab = 'llm';
  const secretField = (id, title) => '<label for="' + id + '">' + title + '<span>仅本页会话，不会保存到磁盘</span></label><div class="password-field"><input id="' + id + '" type="password" autocomplete="new-password" placeholder="原型中可留空" spellcheck="false"><button type="button" class="icon-btn" data-reveal="' + id + '" aria-label="显示或隐藏密钥">' + icon('eye') + '</button></div>';
  $('settingsPanes').innerHTML =
    '<section class="settings-pane" data-pane="llm"><p class="settings-description">配置对话 Agent 使用的模型。主模型与检索模型独立设置。</p>' +
    '<label for="llmProvider">接口类型</label><select id="llmProvider"><option value="compatible">OpenAI 兼容接口</option><option value="local">本地兼容服务</option></select>' +
    '<label for="llmEndpoint">Base URL</label><input id="llmEndpoint" type="url" placeholder="https://api.example.com/v1" spellcheck="false">' +
    '<label for="llmModel">模型 ID</label><input id="llmModel" placeholder="填写供应商提供的模型 ID" spellcheck="false">' +
    secretField('llmKey', 'API Key') +
    '<div class="settings-help">此页仅验证配置格式，不会连接模型或消耗额度。地址与模型名称可保存到本机浏览器；密钥仅保留在当前页面内存，刷新后清空。正式版将由本地后端保管密钥。</div></section>' +
    '<section class="settings-pane hidden" data-pane="embedding"><p class="settings-description">用于查找相关段落。精确财务数值仍通过数据库查询。</p>' +
    '<label class="toggle-row" for="embeddingEnabled"><span>启用 Embedding 检索</span><input type="checkbox" id="embeddingEnabled"></label>' +
    '<div id="embeddingFields"><label for="embeddingEndpoint">Base URL</label><input id="embeddingEndpoint" type="url" placeholder="https://api.example.com/v1" spellcheck="false">' +
    '<label for="embeddingModel">Embedding 模型 ID</label><input id="embeddingModel" placeholder="填写向量模型 ID" spellcheck="false">' +
    secretField('embeddingKey', 'API Key') +
    '<label for="embeddingDimensions">向量维度<span>可选；以模型实际输出为准</span></label><input id="embeddingDimensions" type="number" min="1" max="65536" placeholder="自动识别"></div>' +
    '<div class="settings-help">未启用时可先使用关键词和结构化查询。更换向量模型或维度后，正式版需要重新建立向量索引。</div></section>' +
    '<section class="settings-pane hidden" data-pane="ocr"><p class="settings-description">表格直接读取单元格；扫描图片才需要 OCR。</p>' +
    '<label for="ocrMode">OCR 方式</label><select id="ocrMode"><option value="local">本地解析 / 本地 OCR</option><option value="api">远程 OCR 服务</option></select>' +
    '<div id="ocrApiFields"><label for="ocrEndpoint">OCR 服务地址</label><input id="ocrEndpoint" type="url" placeholder="https://ocr.example.com/parse" spellcheck="false">' +
    '<label for="ocrModel">OCR 模型 / 服务 ID<span>可选</span></label><input id="ocrModel" placeholder="按服务配置填写" spellcheck="false">' +
    secretField('ocrKey', 'API Key') + '</div>' +
    '<div class="format-list"><div><b>Excel / CSV / TSV</b><span>读取工作表、行列与单元格，保留位置与原始值。</span></div><div><b>文本型 PDF</b><span>先提取文本与表格，保留页码。</span></div><div><b>扫描页 / 图片</b><span>调用所选 OCR，再做字段校验。</span></div></div>' +
    '<div class="settings-help">当前原型提供 CSV/TSV 的本地预览。Excel、PDF 和 OCR 的实际解析服务尚未接入。</div></section>' +
    '<section class="settings-pane hidden" data-pane="runtime"><p class="settings-description">设置单次分析的执行上限。正式版由后端执行限制。</p>' +
    '<label for="maxCalls">每次任务最多工具调用次数</label><input id="maxCalls" type="number" min="1" max="100">' +
    '<label for="runTimeout">单个分析容器超时<span>秒</span></label><input id="runTimeout" type="number" min="10" max="600">' +
    '<label for="runBudget">单次模型费用上限<span>人民币元，可选</span></label><input id="runBudget" type="number" min="0.01" step="0.01" placeholder="接入供应商计费后启用">' +
    '<div class="format-list"><div><b>独立科学计算容器</b><span>预装数据分析与绘图库；输入只读、默认断网。</span></div><div><b>密钥与数据库</b><span>容器不接收模型密钥，也不直接挂载项目数据库。</span></div></div>' +
    '<div class="settings-help">这些选项目前是设计配置；尚未运行分析容器，未验证资源限制。</div></section>';
  function updateConditionalFields() {
    $('embeddingFields').classList.toggle('hidden', !$('embeddingEnabled').checked);
    $('ocrApiFields').classList.toggle('hidden', $('ocrMode').value !== 'api');
  }
  function setSettingsTab(tab) {
    settingsTab = tab;
    const titles = { llm: '主模型 API', embedding: 'Embedding API', ocr: '文档与 OCR', runtime: '运行限制' };
    $('settingsTitle').textContent = titles[tab];
    document.querySelectorAll('[data-settings]').forEach(b => b.classList.toggle('active', b.dataset.settings === tab));
    document.querySelectorAll('[data-pane]').forEach(p => p.classList.toggle('hidden', p.dataset.pane !== tab));
    $('settingsResult').textContent = '';
    $('settingsResult').classList.remove('error');
    $('settingsForm').scrollTop = 0;
  }
  function openSettings() {
    closeMenus(); $('app').classList.remove('mobile-sidebar');
    for (const key of Object.keys(defaults)) {
      if (typeof defaults[key] === 'boolean') $(key).checked = config[key];
      else $(key).value = config[key];
    }
    for (const key of Object.keys(secrets)) { $(key).value = secrets[key]; $(key).type = 'password'; }
    updateConditionalFields(); setSettingsTab('llm');
    $('settingsDialog').showModal();
  }
  function readDraft() {
    const draft = {};
    for (const key of Object.keys(defaults)) draft[key] = typeof defaults[key] === 'boolean' ? $(key).checked : $(key).value.trim();
    return draft;
  }
  function validateEndpoint(value, label) {
    if (!value) return label + '不能为空。';
    let url;
    try { url = new URL(value); } catch { return label + '需要填写完整 URL。'; }
    if (url.username || url.password || url.search || url.hash) return label + '不能包含凭据、查询参数或片段；密钥请填入 API Key。';
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) return label + '需要 HTTPS；本机服务可使用 HTTP。';
    return '';
  }
  function validatePanel(draft, tab, mustFill = false) {
    if (tab === 'llm' && (mustFill || draft.llmEndpoint || draft.llmModel || $('llmKey').value)) {
      return validateEndpoint(draft.llmEndpoint, '主模型 Base URL') || (!draft.llmModel ? '请填写主模型 ID。' : '');
    }
    if (tab === 'embedding' && draft.embeddingEnabled) {
      const error = validateEndpoint(draft.embeddingEndpoint, 'Embedding Base URL') || (!draft.embeddingModel ? '请填写 Embedding 模型 ID。' : '');
      if (error) return error;
      if (draft.embeddingDimensions && (!Number.isInteger(Number(draft.embeddingDimensions)) || Number(draft.embeddingDimensions) < 1 || Number(draft.embeddingDimensions) > 65536)) return '向量维度应为 1–65536 的整数。';
    }
    if (tab === 'ocr' && draft.ocrMode === 'api') return validateEndpoint(draft.ocrEndpoint, 'OCR 服务地址');
    if (tab === 'runtime') {
      const count = Number(draft.maxCalls), timeout = Number(draft.runTimeout), budget = Number(draft.runBudget);
      if (!Number.isInteger(count) || count < 1 || count > 100) return '工具调用次数应为 1–100 的整数。';
      if (!Number.isInteger(timeout) || timeout < 10 || timeout > 600) return '容器超时应为 10–600 秒的整数。';
      if (draft.runBudget && (!Number.isFinite(budget) || budget <= 0)) return '费用上限需要大于 0。';
    }
    return '';
  }
  function configResult(text, error = false) {
    $('settingsResult').textContent = text; $('settingsResult').classList.toggle('error', error);
    $('settingsResult').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  function updateModelLabel() {
    $('modelLabel').textContent = config.llmModel || '选择模型';
    $('currentModel').textContent = config.llmModel ? config.llmModel + ' · 未连接' : '尚未配置';
    $('apiStatus').textContent = config.llmModel ? '配置已保存 · 未连接' : '主模型 · Embedding · OCR';
  }
  $('checkConfig').onclick = () => {
    const error = validatePanel(readDraft(), settingsTab, true);
    configResult(error || '配置格式检查通过。未发起网络请求，尚未验证连接或密钥。', !!error);
  };
  $('settingsForm').onsubmit = e => {
    e.preventDefault();
    const draft = readDraft();
    for (const tab of ['llm', 'embedding', 'ocr', 'runtime']) {
      const error = validatePanel(draft, tab, tab === settingsTab && tab === 'llm');
      if (error) { setSettingsTab(tab); configResult(error, true); return; }
    }
    config = draft;
    for (const key of Object.keys(secrets)) secrets[key] = $(key).value.trim();
    let persistent = true;
    try { localStorage.setItem(configKey, JSON.stringify(config)); } catch { persistent = false; }
    updateModelLabel();
    configResult((persistent ? '非敏感配置已保存到本机浏览器。' : '浏览器禁用了存储，配置仅保留在当前页面。') + '密钥仅保留在页面内存；未连接 API。');
  };
  document.querySelectorAll('[data-settings]').forEach(b => b.onclick = () => setSettingsTab(b.dataset.settings));
  document.querySelectorAll('[data-reveal]').forEach(b => b.onclick = () => {
    const field = $(b.dataset.reveal); field.type = field.type === 'password' ? 'text' : 'password';
    b.setAttribute('aria-pressed', String(field.type === 'text'));
  });
  $('embeddingEnabled').onchange = updateConditionalFields;
  $('ocrMode').onchange = updateConditionalFields;
  $('apiEntry').onclick = openSettings; $('topApi').onclick = openSettings; $('modelSettings').onclick = openSettings;
  $('closeSettings').onclick = () => $('settingsDialog').close();
  [$('settingsDialog'), $('benchmarkDialog')].forEach(dialog => dialog.addEventListener('click', e => {
    if (e.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) dialog.close();
  }));
  updateModelLabel();

  $('newChat').onclick = newChat;
  $('library').onclick = () => openDrawer('files');
  $('openFiles').onclick = () => openDrawer('files');
  $('closeDrawer').onclick = closeDrawer;
  document.querySelectorAll('[data-drawer]').forEach(b => b.onclick = () => openDrawer(b.dataset.drawer));
  $('attachButton').onclick = () => showMenu('attachMenu', 'attachButton');
  $('uploadFile').onclick = () => { closeMenus(); $('fileInput').click(); };
  $('fileInput').onchange = () => { addFiles([...$('fileInput').files]); $('fileInput').value = ''; };
  $('useSample').onclick = async () => {
    await addFiles([new File([sampleText], '美的集团_2023-2024_示例.csv', { type: 'text/csv' })], true);
    if (!$('messageInput').value.trim()) $('messageInput').value = '比较2024年与2023年的财务表现，并标明证据来源。';
    updateComposer();
  };
  $('sendButton').onclick = sendMessage;
  $('messageInput').oninput = updateComposer;
  $('messageInput').onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault(); if (!state.busy) sendMessage();
    }
  };
  document.querySelectorAll('[data-prompt]').forEach(b => b.onclick = () => {
    $('messageInput').value = b.dataset.prompt; updateComposer(); $('messageInput').focus();
  });
  $('collapseSidebar').onclick = () => {
    if (matchMedia('(max-width:850px)').matches) $('app').classList.remove('mobile-sidebar');
    else $('app').classList.add('sidebar-collapsed');
  };
  $('expandSidebar').onclick = () => {
    $('app').classList.remove('sidebar-collapsed');
    if (matchMedia('(max-width:850px)').matches) $('app').classList.add('mobile-sidebar');
  };
  $('sidebarScrim').onclick = () => $('app').classList.remove('mobile-sidebar');
  $('modelButton').onclick = () => showMenu('modelMenu', 'modelButton');
  $('benchmark').onclick = () => { $('app').classList.remove('mobile-sidebar'); $('benchmarkDialog').showModal(); };
  $('closeBenchmark').onclick = () => $('benchmarkDialog').close();
  document.addEventListener('click', e => {
    if (!e.target.closest('#composer')) showMenu('attachMenu', 'attachButton', false);
    if (!e.target.closest('.top-left') && !e.target.closest('#modelMenu')) showMenu('modelMenu', 'modelButton', false);
  });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { e.preventDefault(); newChat(); }
    if (e.key === 'Escape') { closeMenus(); closeDrawer(); $('app').classList.remove('mobile-sidebar'); }
  });
  let dragDepth = 0;
  document.addEventListener('dragenter', e => {
    if (![...(e.dataTransfer?.types || [])].includes('Files')) return;
    e.preventDefault(); dragDepth++;
    if (!document.querySelector('dialog[open]')) $('dropOverlay').classList.remove('hidden');
  });
  document.addEventListener('dragover', e => { if ([...(e.dataTransfer?.types || [])].includes('Files')) e.preventDefault(); });
  document.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('dropOverlay').classList.add('hidden'); } });
  document.addEventListener('drop', e => {
    if (!e.dataTransfer?.files.length) return;
    e.preventDefault(); dragDepth = 0; $('dropOverlay').classList.add('hidden');
    if (!document.querySelector('dialog[open]')) addFiles([...e.dataTransfer.files]);
  });
  $('messageInput').addEventListener('paste', e => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  newChat();
  function applyHashRoute() {
    if (location.hash === '#example') {
      $('settingsDialog').close();
      $('benchmarkDialog').close();
      openExample();
    }
    if (location.hash === '#settings' && !$('settingsDialog').open) openSettings();
  }
  addEventListener('hashchange', applyHashRoute);
  applyHashRoute();
})();
