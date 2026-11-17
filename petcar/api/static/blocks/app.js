/* petcar 积木编程页面逻辑 */
(function () {
  'use strict';

  const STORAGE_KEY = 'petcar.blocks.program.v1';

  let workspace = null;
  let schema = null;
  let lastLogId = 0;
  let currentRunId = 0;
  let running = false;
  let pollTimer = null;
  let saveTimer = null;
  let lastBlockId = null;
  let videoOn = true;      // 视频开关
  let viewEnterSent = false;
  let codePanelVisible = true;  // 代码窗可见性
  let codeTimer = null;

  const $ = (id) => document.getElementById(id);
  const consoleEl = $('console');

  // ==========================================================================
  // 初始化
  // ==========================================================================
  async function init() {
    if (typeof Blockly === 'undefined') {
      throw new Error('Blockly 资源加载失败，请检查 static/blocks/vendor/blockly');
    }

    schema = await fetch('/api/blocks/schema').then((r) => r.json());
    const define = (Blockly.common && Blockly.common.defineBlocksWithJsonArray)
      ? Blockly.common.defineBlocksWithJsonArray.bind(Blockly.common)
      : Blockly.defineBlocksWithJsonArray;
    define(schema.blocks.map((b) => b.blockly));

    const contents = schema.categories.map((cat) => ({
      kind: 'category',
      name: cat.label,
      colour: cat.colour,
      contents: schema.blocks
        .filter((b) => b.category === cat.id)
        .map((b) => ({ kind: 'block', type: b.type })),
    }));

    workspace = Blockly.inject('blocklyDiv', {
      toolbox: { kind: 'categoryToolbox', contents },
      renderer: 'zelos',
      grid: { spacing: 24, length: 2, colour: '#cbd5e1', snap: true },
      zoom: { controls: true, wheel: true, startScale: 0.9, maxScale: 2.0, minScale: 0.4 },
      trashcan: true, sounds: false,
      media: '/static/blocks/vendor/blockly/media/',
      move: { scrollbars: true, drag: true, wheel: true },
    });

    buildColorChips();
    loadProgram();
    workspace.addChangeListener(onWorkspaceChange);
    bindButtons();
    bindModal();

    // --- 给 Toolbox / Flyout 删除区加视觉反馈 ---
    hookDeleteAreaVisual();

    // --- Python 代码实时预览 ---
    try {
      registerPythonGenerators();
    } catch (e) {
      appendLog({ ts: nowText(), level: 'warn', text: 'Python 生成器加载失败: ' + e.message });
    }
    setCodePanelVisible(true);
    scheduleCodeUpdate();

    setRunning(false);
    appendLog({ ts: nowText(), level: 'info', text: '积木编辑器已就绪' });

    // 视频默认开
    setVideo(true);

    // 通知后端：积木页进入 → 中控面板自动关自己的视频
    enterBlocksView();

    // 页面关闭/切换时通知后端
    window.addEventListener('beforeunload', exitBlocksView);

    pollStatus();
  }

  function nowText() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  // ==========================================================================
  // 积木页视图锁（告诉后端中控面板关自己的视频）
  // ==========================================================================
  async function enterBlocksView() {
    if (viewEnterSent) return;
    try {
      await fetch('/api/blocks/view', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'enter' }),
      });
      viewEnterSent = true;
    } catch (e) { /* ignore */ }
  }

  async function exitBlocksView() {
    try {
      await fetch('/api/blocks/view', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'exit' }),
      });
    } catch (e) { /* ignore */ }
  }

  // ==========================================================================
  // 视频开关
  // ==========================================================================
  function setVideo(on) {
    videoOn = !!on;
    const img = $('video-img');
    const wrap = $('video-wrap');
    const ph = $('video-off-placeholder');
    const btn = $('btn-video-toggle');
    if (on) {
      // 显式清掉 inline display:none (之前的 onerror 残留, 浏览器损坏帧会触发)
      img.style.display = '';
      img.src = '/api/video_feed?t=' + Date.now();
      wrap.classList.remove('hidden');
      ph.classList.add('hidden');
      btn.textContent = '■ 关闭视频';
      btn.classList.add('active');
    } else {
      img.removeAttribute('src');
      wrap.classList.add('hidden');
      ph.classList.remove('hidden');
      btn.textContent = '▶ 打开视频';
      btn.classList.remove('active');
    }
  }

  // ==========================================================================
  // 动态颜色 chip（根据 schema.colors）
  // ==========================================================================
  function buildColorChips() {
    const container = $('color-chips');
    if (!container || !schema.colors) return;
    const list = schema.colors.slice(0, 4);
    container.innerHTML = '';
    list.forEach((c) => {
      const sp = document.createElement('span');
      sp.id = 'see-color-' + c.key;
      sp.className = 'chip color-chip';
      sp.textContent = c.label;
      container.appendChild(sp);
    });
  }

  // ==========================================================================
  // 程序保存 / 加载
  // ==========================================================================
  function loadProgram() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        Blockly.serialization.workspaces.load(JSON.parse(saved), workspace);
        appendLog({ ts: nowText(), level: 'info', text: '已恢复上次的积木' });
        return;
      } catch (e) {
        appendLog({ ts: nowText(), level: 'warn', text: '本地草稿损坏，已加载示例' });
      }
    }
    loadStarter();
  }

  function loadStarter() {
    Blockly.serialization.workspaces.load({
      blocks: { blocks: [{
        type: 'event_start', id: 'start', x: 40, y: 40,
        next: { block: {
          type: 'move_for', id: 'move1',
          fields: { DIR: 'forward', SPEED: 150, SECONDS: 1 },
          next: { block: {
            type: 'show_emotion', id: 'emotion1',
            fields: { EMOTION: 'happy' },
          }},
        }},
      }]},
    }, workspace);
  }

  function saveDraft() {
    if (!workspace) return;
    try {
      const program = Blockly.serialization.workspaces.save(workspace);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(program));
    } catch (e) { /* ignore */ }
  }

  function onWorkspaceChange(event) {
    if (event && event.isUiEvent) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 500);
    scheduleCodeUpdate();
  }

  function scheduleCodeUpdate() {
    clearTimeout(codeTimer);
    codeTimer = setTimeout(updateCodeView, 200);
  }

  // ==========================================================================
  // 运行控制
  // ==========================================================================
  async function runProgram() {
    if (!workspace || running) return;
    clearHighlight();
    const program = Blockly.serialization.workspaces.save(workspace);
    try {
      const res = await fetch('/api/blocks/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ program }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        if (data.errors && data.errors.length) { showErrors(data.errors); }
        else { appendLog({ ts: nowText(), level: 'error', text: data.message || '运行失败' }); }
        return;
      }
      currentRunId = data.run_id;
      lastLogId = 0;
      appendLog({ ts: nowText(), level: 'info', text: `开始运行，共 ${data.blocks} 块积木` });
      setRunning(true);
      pollStatusNow();
    } catch (e) {
      appendLog({ ts: nowText(), level: 'error', text: '无法连接小车: ' + e });
    }
  }

  async function stopProgram(estop) {
    const url = estop ? '/api/blocks/estop' : '/api/blocks/stop';
    try {
      await fetch(url, { method: 'POST' });
      appendLog({ ts: nowText(), level: estop ? 'warn' : 'info',
                  text: estop ? '已发送急停' : '已发送停止' });
      pollStatusNow();
    } catch (e) {
      appendLog({ ts: nowText(), level: 'error', text: '停止失败: ' + e });
    }
  }

  function setRunning(value) {
    running = value;
    const runBtn = $('btn-run');
    const stopBtn = $('btn-stop');
    if (runBtn) runBtn.disabled = value;
    if (stopBtn) stopBtn.disabled = !value;
    const badge = $('stateBadge');
    if (badge) {
      badge.textContent = value ? '运行中' : '空闲';
      badge.className = 'badge ' + (value ? 'running' : 'idle');
    }
  }

  // ==========================================================================
  // 状态轮询
  // ==========================================================================
  function pollStatusNow() {
    clearTimeout(pollTimer); pollStatus();
  }

  async function pollStatus() {
    try {
      const res = await fetch(`/api/blocks/status?since=${lastLogId}`);
      const s = await res.json();
      setConnected(true);
      applyStatus(s);
    } catch (e) {
      setConnected(false);
    } finally {
      clearTimeout(pollTimer);
      pollTimer = setTimeout(pollStatus, running ? 250 : 900);
    }
  }

  function applyStatus(s) {
    if (s.run_id > currentRunId) { currentRunId = s.run_id; lastLogId = 0; }
    if (s.run_id < currentRunId) return;

    const wasRunning = running;
    const isRunning = s.state === 'running';
    if (isRunning !== running) setRunning(isRunning);

    // 停止/急停时: 清空识别 chips (需求 4)
    if (wasRunning && !isRunning) {
      resetAllChips();
    }

    const elapsed = $('elapsed');
    if (elapsed) {
      elapsed.textContent = isRunning
        ? `${Number(s.elapsed || 0).toFixed(1)}s` : '0.0s';
    }

    if (Array.isArray(s.logs)) {
      for (const item of s.logs) {
        if (item.id > lastLogId) { appendLog(item); lastLogId = item.id; }
      }
    }

    if (isRunning) highlightBlock(s.current_block || null);
    else highlightBlock(null);

    const sees = s.sees || {};
    // stale = 画面久没更新 → 强制灰掉所有 chip
    const stale = !!sees.stale;
    setChip('see-face', !stale && !!sees.face);
    setChip('see-tennis', !stale && !!sees.tennis);

    const colors = sees.colors || {};
    Object.keys(colors).forEach((k) => {
      const el = $('see-color-' + k);
      if (el) el.classList.toggle('on', !stale && !!colors[k].visible);
    });
  }

  function resetAllChips() {
    setChip('see-face', false);
    setChip('see-tennis', false);
    document.querySelectorAll('#color-chips .chip').forEach((el) => {
      el.classList.remove('on');
    });
  }

  // ==========================================================================
  // 高亮 / 错误
  // ==========================================================================
  function highlightBlock(id) {
    if (!workspace || id === lastBlockId) return;
    try { if (lastBlockId) workspace.highlightBlock(null); } catch (e) { /* ignore */ }
    lastBlockId = id;
    if (id) { try { workspace.highlightBlock(id); } catch (e) { /* ignore */ } }
  }
  function clearHighlight() {
    try { if (workspace && lastBlockId) workspace.highlightBlock(null); } catch (e) { /* ignore */ }
    lastBlockId = null;
  }
  function showErrors(errors) {
    errors.forEach((item) => {
      appendLog({ ts: nowText(), level: 'error', text: item.message || '积木有误' });
      if (item.blockId && workspace) {
        try { workspace.centerOnBlock(item.blockId); highlightBlock(item.blockId); }
        catch (e) { /* ignore */ }
      }
    });
  }

  // ==========================================================================
  // 控制台 / 连接状态
  // ==========================================================================
  function appendLog(item) {
    if (!consoleEl) return;
    const row = document.createElement('div');
    row.className = 'log ' + (item.level || 'info');
    if (item.ts) {
      const t = document.createElement('span');
      t.className = 't'; t.textContent = item.ts;
      row.appendChild(t);
    }
    row.appendChild(document.createTextNode(item.text || ''));
    consoleEl.appendChild(row);
    while (consoleEl.children.length > 300) consoleEl.removeChild(consoleEl.firstChild);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
  function clearConsole() {
    if (consoleEl) consoleEl.innerHTML = '';
  }
  function setConnected(ok) {
    const el = $('conn'); if (!el) return;
    el.textContent = ok ? '已连接' : '未连接';
    el.className = 'conn ' + (ok ? 'on' : 'off');
  }
  function setChip(id, on) {
    const el = $(id); if (el) el.classList.toggle('on', !!on);
  }

  // ==========================================================================
  // 拖入 Toolbox / Flyout 时叠加半透明层 + 垃圾桶开盖/关盖动画
  // Blockly 原生会自动删除积木（DeleteArea 机制），我们只管视觉
  // ==========================================================================
  function hookDeleteAreaVisual() {
    // 复用的覆盖层 DOM（只创建一次）
    let overlay = null;

    function getOverlay() {
      // 检查之前创建的还在不在 DOM 里（防止游离）
      if (overlay && document.body.contains(overlay)) return overlay;
      overlay = document.createElement('div');
      overlay.className = 'tb-drop-overlay';
      overlay.innerHTML = `
        <div class="tb-drop-bg"></div>
        <div class="tb-drop-trash">
          <svg viewBox="0 0 120 130" width="60" height="65">
            <g class="tb-trash-lid">
              <rect x="28" y="14" width="64" height="14" rx="3" fill="#475569"/>
              <rect x="50" y="6"  width="20" height="10" rx="3" fill="#334155"/>
            </g>
            <g class="tb-trash-body">
              <path d="M26 30 L32 112 Q34 118 40 118 L80 118 Q86 118 88 112 L94 30 Z" fill="#475569"/>
              <rect x="46" y="50" width="8" height="56" rx="2" fill="#fff" opacity="0.7"/>
              <rect x="66" y="50" width="8" height="56" rx="2" fill="#fff" opacity="0.7"/>
            </g>
          </svg>
        </div>
      `;
      overlay.style.display = 'none';
      overlay.style.pointerEvents = 'none';   // 不能拦截 Blockly 拖拽事件
      document.body.appendChild(overlay);
      return overlay;
    }

    function positionOverlay(target) {
      // Blockly 新版本 getClientRect() 返回 sentinel 值（内部坐标系），
      // 必须用 DOM 元素的 getBoundingClientRect() 拿屏幕坐标
      const domSelector =
        target === workspace.toolbox  ? '.blocklyToolboxDiv' :
        '.blocklyFlyout, .blocklyFlyoutScrollbar';
      const domEl = document.querySelector(domSelector);
      if (!domEl) return false;
      const rect = domEl.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return false;  // 隐藏状态
      const el = getOverlay();
      el.style.position = 'fixed';
      el.style.left   = rect.left   + 'px';
      el.style.top    = rect.top    + 'px';
      el.style.width  = rect.width  + 'px';
      el.style.height = rect.height + 'px';
      el.style.zIndex = '99999';
      return true;
    }

    function show(target) {
      const el = getOverlay();
      if (!positionOverlay(target)) return;
      el.style.display = 'flex';
      el.offsetHeight;  // reflow
      el.classList.remove('is-closing');
      el.classList.add('is-open');
    }

    function hide(animated = false) {
      const el = getOverlay();
      if (!el || el.style.display === 'none') return;
      if (animated) {
        el.classList.remove('is-open');
        el.classList.add('is-closing');
        setTimeout(() => { el.style.display = 'none'; el.classList.remove('is-closing'); }, 220);
      } else {
        el.style.display = 'none';
        el.classList.remove('is-open', 'is-closing');
      }
    }

    const attachTo = (target) => {
      if (!target) return;
      // Blockly 新版本实际调用 onDragEnter / onDragExit（不是 onDragOver！）
      const origEnter = target.onDragEnter?.bind(target);
      const origExit  = target.onDragExit?.bind(target);
      const origDrop  = target.onDrop?.bind(target);

      target.onDragEnter = function (e) {
        origEnter?.(e);
        show(target);
      };
      target.onDragExit = function (e) {
        origExit?.(e);
        hide(false);
      };
      target.onDrop = function (e) {
        origDrop?.(e);
        hide(true);
      };
    };

    attachTo(workspace.toolbox);
    if (workspace.flyout_) attachTo(workspace.flyout_);
    if (workspace.flyout && workspace.flyout !== workspace.flyout_) attachTo(workspace.flyout);

    // 全局兜底：mouseup 时一定清理
    document.addEventListener('mouseup', () => hide(false));
  }

  // ==========================================================================
  // 文件管理 Modal
  // ==========================================================================
  let _modalTab = 'open';
  function openModal(tab = 'open') {
    $('modal-mask').classList.remove('hidden');
    switchTab(tab);
    if (tab === 'open') loadFileList();
    if (tab === 'save') { $('save-name').value = suggestDefaultName(); setTimeout(() => $('save-name').focus(), 50); }
  }
  function closeModal() { $('modal-mask').classList.add('hidden'); }
  function bindModal() {
    $('modal-close').addEventListener('click', closeModal);
    $('modal-mask').addEventListener('click', (e) => { if (e.target.id === 'modal-mask') closeModal(); });
    document.querySelectorAll('.tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    $('btn-save-confirm').addEventListener('click', onSaveConfirm);
    $('save-name').addEventListener('keydown', (e) => { if (e.key === 'Enter') onSaveConfirm(); });
  }
  function switchTab(tab) {
    _modalTab = tab;
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + tab));
    if (tab === 'open') loadFileList();
    if (tab === 'save') $('save-name').value = suggestDefaultName();
  }
  function suggestDefaultName() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return `积木程序_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
  }

  async function loadFileList() {
    $('list-examples').innerHTML = '<li class="fs-item"><span class="fs-name">加载中...</span></li>';
    try {
      const r = await fetch('/api/blocks/files'); const j = await r.json();
      renderFileList('list-examples', j.examples || [], true);
      renderFileList('list-user', j.user || [], false);
    } catch (e) {
      appendLog({ ts: nowText(), level: 'error', text: '加载文件列表失败: ' + e });
      $('list-examples').innerHTML = ''; $('list-user').innerHTML = '';
    }
  }
  function renderFileList(listId, items, readonly) {
    const ul = $(listId); ul.innerHTML = '';
    if (!items || items.length === 0) {
      const li = document.createElement('li'); li.className = 'fs-item readonly';
      li.innerHTML = '<span class="fs-name" style="color:#7b8ba8">（空）</span>';
      ul.appendChild(li); return;
    }
    items.forEach((f) => {
      const li = document.createElement('li');
      li.className = 'fs-item' + (readonly ? ' readonly' : '');
      li.innerHTML = `<span class="fs-name">${escapeHtml(f.name)}</span>
        <span class="fs-meta">${f.mtime_text || ''}</span><span class="fs-actions"></span>`;
      li.addEventListener('dblclick', () => openFile(f.path, readonly));
      const actions = li.querySelector('.fs-actions');
      if (!readonly) {
        const del = document.createElement('button');
        del.className = 'btn btn-sm'; del.textContent = '删除';
        del.addEventListener('click', (e) => { e.stopPropagation(); deleteUserFile(f.path); });
        const dl = document.createElement('button');
        dl.className = 'btn btn-sm'; dl.textContent = '下载';
        dl.addEventListener('click', (e) => { e.stopPropagation(); window.location.href = '/api/blocks/files/export?path=' + encodeURIComponent(f.path); });
        actions.appendChild(del); actions.appendChild(dl);
      } else {
        const dl = document.createElement('button');
        dl.className = 'btn btn-sm'; dl.textContent = '下载';
        dl.addEventListener('click', (e) => { e.stopPropagation(); window.location.href = '/api/blocks/files/export?path=' + encodeURIComponent(f.path); });
        actions.appendChild(dl);
      }
      ul.appendChild(li);
    });
  }

  async function openFile(path, readonly) {
    try {
      const r = await fetch('/api/blocks/files/content?path=' + encodeURIComponent(path));
      const j = await r.json();
      if (!j.ok) { appendLog({ ts: nowText(), level: 'error', text: j.error || '打开失败' }); return; }
      Blockly.serialization.workspaces.load(j.program, workspace);
      saveDraft(); closeModal();
      appendLog({ ts: nowText(), level: 'info', text: `已打开 ${path}${readonly ? '（只读示例）' : ''}` });
    } catch (e) { appendLog({ ts: nowText(), level: 'error', text: '打开文件失败: ' + e }); }
  }
  async function deleteUserFile(path) {
    if (!confirm(`确认删除 ${path} ？`)) return;
    try {
      const r = await fetch('/api/blocks/files/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
      const j = await r.json();
      if (j.ok) { appendLog({ ts: nowText(), level: 'info', text: `已删除 ${path}` }); loadFileList(); }
      else appendLog({ ts: nowText(), level: 'error', text: j.error || '删除失败' });
    } catch (e) { appendLog({ ts: nowText(), level: 'error', text: '删除失败: ' + e }); }
  }
  async function onSaveConfirm() {
    const name = $('save-name').value.trim();
    if (!name) { alert('请输入文件名'); return; }
    const program = Blockly.serialization.workspaces.save(workspace);
    try {
      const r = await fetch('/api/blocks/files/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, program }) });
      const j = await r.json();
      if (j.ok) { saveDraft(); appendLog({ ts: nowText(), level: 'info', text: `已保存到 ${j.path}` }); closeModal(); }
      else alert(j.error || '保存失败');
    } catch (e) { alert('保存失败: ' + e); }
  }
  function escapeHtml(s) {
    return String(s).replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  // ==========================================================================
  // 按钮
  // ==========================================================================
  function bindButtons() {
    $('btn-run').addEventListener('click', runProgram);
    $('btn-stop').addEventListener('click', () => stopProgram(false));
    $('btn-estop').addEventListener('click', () => stopProgram(true));
    $('btn-video-toggle').addEventListener('click', () => setVideo(!videoOn));
    $('btn-clear-console').addEventListener('click', clearConsole);

    $('btn-new').addEventListener('click', () => {
      if (!confirm('新建会清空当前积木，确定吗？')) return;
      workspace.clear(); localStorage.removeItem(STORAGE_KEY);
      loadStarter(); clearConsole(); resetAllChips();
    });

    $('btn-open').addEventListener('click', () => openModal('open'));
    $('btn-save').addEventListener('click', () => openModal('save'));

    $('btn-import').addEventListener('click', () => $('fileInput').click());
    $('fileInput').addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0]; e.target.value = '';
      if (!file) return;
      try {
        const program = JSON.parse(await file.text());
        Blockly.serialization.workspaces.load(program, workspace);
        saveDraft(); appendLog({ ts: nowText(), level: 'info', text: `已导入 ${file.name}` });
      } catch (err) { appendLog({ ts: nowText(), level: 'error', text: '导入失败: ' + err }); }
    });

    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); runProgram(); }
      else if (e.key === 'Escape') {
        if (!$('modal-mask').classList.contains('hidden')) closeModal();
        else { e.preventDefault(); stopProgram(false); }
      }
    });

    // --- 代码窗按钮（旧内联工具栏按钮已删除，只保留顶部 🐍 代码 按钮） ---
    $('btn-code-toggle-top').addEventListener('click', () => setCodePanelVisible(!codePanelVisible));
  }

  // ==========================================================================
  // Python 代码实时预览（仿编程猫）
  // ==========================================================================

  function setCodePanelVisible(visible) {
    codePanelVisible = !!visible;
    const section = $('codeSection');
    const layout = document.querySelector('.layout');
    const btnTop = $('btn-code-toggle-top');
    const btn = $('btn-code-toggle');
    if (section) section.classList.toggle('hidden-code', !visible);
    if (layout)  layout.classList.toggle('no-code', !visible);
    if (btnTop)  btnTop.classList.toggle('active', visible);
    if (btn)     btn.textContent = visible ? '▼' : '▶';

    // 等 CSS grid 过渡完成再让 Blockly 重新测量父容器
    setTimeout(() => {
      if (typeof Blockly !== 'undefined' && workspace) {
        try { Blockly.svgResize(workspace); } catch (e) {}
      }
      window.dispatchEvent(new Event('resize'));
    }, 260);   // 与 CSS transition 时长对齐
  }

  function copyGeneratedCode() {
    const view = $('code-view');
    if (!view) return;
    // 从 data-code 属性取原始代码（高亮用 HTML，复制用原文）
    const raw = view.getAttribute('data-code') || view.textContent;
    const textarea = document.createElement('textarea');
    textarea.value = raw; document.body.appendChild(textarea);
    textarea.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(textarea);
    // 新 API 备用
    if (!ok && navigator.clipboard) {
      navigator.clipboard.writeText(raw).catch(() => {});
      ok = true;
    }
    const btn = $('btn-copy-code');
    if (btn) {
      btn.textContent = ok ? '✅' : '❌';
      setTimeout(() => { btn.textContent = '📋'; }, 1200);
    }
  }

  function updateCodeView() {
    const view = $('code-view');
    if (!view || !workspace) return;
    let code = '';
    try {
      const P = Blockly.Python || Blockly.PythonGenerator;
      if (!P) {
        code = '# Python 生成器未加载';
      } else {
        let raw = String(P.workspaceToCode(workspace) || '');
        raw = raw.replace(/__PETCAR_START__\s*\n?/g, '').trim();
        if (raw) {
          // 把所有顶层代码缩进一层，包进 def petcar_program()
          const INDENT = '  ';
          const lines = raw.split('\n');
          const indented = lines.map((ln) => ln.trim() ? INDENT + ln : '');
          code = '# 🤖 由 AITank 积木自动生成\n' +
                 'def petcar_program():\n' +
                 indented.join('\n') + '\n' +
                 '\n# 运行入口\n' +
                 'if __name__ == "__main__":\n' +
                 INDENT + 'petcar_program()\n';
        } else {
          code = '# 🐍 在左侧拖入积木，这里会实时生成 Python 代码\n# （还没有积木哦～）';
        }
      }
    } catch (e) {
      code = '# ⚠️ 代码生成出错: ' + e.message;
    }
    view.setAttribute('data-code', code);
    view.innerHTML = '<code>' + highlightPython(code) + '</code>';
  }

  // -------------------- Blockly Python 生成器注册 --------------------
  // 每个积木的 blockToCode 返回 [string, order] 或 string
  // Blockly Python 生成器约定：
  //   - 语句积木（带 previousStatement/nextStatement）返回 ['code', Blockly.Python.ORDER_ATOMIC]
  //   - 值积木返回 ['code', Blockly.Python.ORDER_xxx]

  function _ensurePython() {
    // 新版 Blockly 可能叫 PythonGenerator，也可能仍暴露 Python 别名
    const P = Blockly.Python || Blockly.PythonGenerator;
    if (!P) {
      throw new Error('Blockly Python 生成器未加载，请确认 python_compressed.js 已引入');
    }
    return P;
  }

  function registerPythonGenerators() {
    const tryOnce = () => {
      if (typeof Blockly === 'undefined') return false;
      const P = Blockly.Python || Blockly.PythonGenerator;
      if (!P || !P.forBlock) return false;
      _doRegister(P);
      _registerOnWorkspaceInstance(P);
      return true;
    };
    if (!tryOnce()) {
      // 延迟重试（python_compressed.js 可能比 blockly_compressed.js 晚加载）
      const iv = setInterval(() => {
        if (tryOnce()) clearInterval(iv);
      }, 100);
    }
  }

  // workspace.getGenerator('Python') 返回独立实例，必须同步注册
  function _registerOnWorkspaceInstance(P) {
    if (!workspace) return;
    let wsGen = null;
    try { wsGen = workspace.getGenerator('Python'); } catch (e) { wsGen = null; }
    if (!wsGen) {
      // 如果 workspace 还没有 Python 生成器，给它装一个
      wsGen = new (Blockly.PythonGenerator || Blockly.Python)();
      try { workspace.setGenerator('Python', wsGen); } catch (e) { /* ignore */ }
    }
    // 把 forBlock 字典合并（不覆盖已注册的）
    if (wsGen.forBlock) {
      for (const key in P.forBlock) {
        if (!wsGen.forBlock[key]) wsGen.forBlock[key] = P.forBlock[key];
      }
    }
  }

  function _doRegister(P) {
    const FB = P.forBlock;
    if (!FB) { console.warn('Python generator has no forBlock dict'); return; }

    // 关键：语句积木（有 previous/nextStatement）只返回字符串
    // 只有值积木（输出到 value 插槽）才返回 [code, order] 数组

    // --- event_start (帽块，语句) ---
    FB['event_start'] = function () {
      return '__PETCAR_START__\n';
    };

    // --- move_for (语句) ---
    FB['move_for'] = function (block) {
      const dir = block.getFieldValue('DIR');
      const speed = block.getFieldValue('SPEED');
      const sec = block.getFieldValue('SECONDS');
      return `petcar.move("${dir}", speed=${speed}, seconds=${sec})\n`;
    };

    // --- move_stop (语句) ---
    FB['move_stop'] = function () {
      return 'petcar.stop()\n';
    };

    // --- wait (语句) ---
    FB['wait'] = function (block) {
      const sec = block.getFieldValue('SECONDS');
      return `petcar.wait(${sec})\n`;
    };

    // --- look (PTZ) (语句) ---
    FB['look'] = function (block) {
      const dir = block.getFieldValue('DIR');
      const deg = block.getFieldValue('DEGREES');
      return `petcar.ptz("${dir}", degrees=${deg})\n`;
    };

    // --- show_emotion (语句) ---
    FB['show_emotion'] = function (block) {
      const emo = block.getFieldValue('EMOTION');
      return `petcar.show_emotion("${emo}")\n`;
    };

    // --- do_action (语句) ---
    FB['do_action'] = function (block) {
      const action = block.getFieldValue('ACTION');
      return `petcar.action("${action}")\n`;
    };

    // --- say (语句) ---
    FB['say'] = function (block) {
      const text = block.getFieldValue('TEXT').replace(/"/g, '\\"');
      return `petcar.say("${text}")\n`;
    };

    // --- photo (语句) ---
    FB['photo'] = function () {
      return 'petcar.photo()\n';
    };

    // --- if_sees (语句) ---
    FB['if_sees'] = function (block) {
      const target = block.getFieldValue('TARGET');
      const body = P.statementToCode(block, 'DO') || '  pass\n';
      return `if petcar.sees("${target}"):\n${body}`;
    };

    // --- if_sees_color (语句) ---
    FB['if_sees_color'] = function (block) {
      const color = block.getFieldValue('COLOR');
      const bodyDo = P.statementToCode(block, 'DO') || '  pass\n';
      const bodyElse = P.statementToCode(block, 'ELSE');
      let code = `if petcar.sees_color("${color}"):\n${bodyDo}`;
      if (bodyElse && bodyElse.trim()) {
        code += `else:\n${bodyElse}`;
      }
      return code;
    };

    // --- if_gesture (语句) ---
    FB['if_gesture'] = function (block) {
      const gesture = block.getFieldValue('GESTURE');
      const bodyDo = P.statementToCode(block, 'DO') || '  pass\n';
      const bodyElse = P.statementToCode(block, 'ELSE');
      let code = `if petcar.sees_gesture("${gesture}"):\n${bodyDo}`;
      if (bodyElse) {
        code += `else:\n${bodyElse}`;
      }
      return code;
    };

    // --- color_track_start (语句) ---
    FB['color_track_start'] = function (block) {
      const color = block.getFieldValue('COLOR');
      return `petcar.color_track("${color}")\n`;
    };

    // --- color_track_stop (语句) ---
    FB['color_track_stop'] = function () {
      return 'petcar.color_track_stop()\n';
    };

    // --- track_start (语句) ---
    FB['track_start'] = function (block) {
      const target = block.getFieldValue('TARGET');
      return `petcar.track("${target}")\n`;
    };

    // --- track_stop (语句) ---
    FB['track_stop'] = function () {
      return 'petcar.track_stop()\n';
    };

    // --- wait_until (语句) ---
    FB['wait_until'] = function (block) {
      const target = block.getFieldValue('TARGET');
      const timeout = block.getFieldValue('TIMEOUT');
      return `petcar.wait_until("${target}", ${timeout})\n`;
    };

    // --- repeat (语句) ---
    FB['repeat'] = function (block) {
      const times = block.getFieldValue('TIMES');
      const body = P.statementToCode(block, 'DO') || '  pass\n';
      return `for _ in range(${times}):\n${body}`;
    };

    // --- forever (语句) ---
    FB['forever'] = function (block) {
      const body = P.statementToCode(block, 'DO') || '  pass\n';
      return `while True:\n${body}`;
    };
  }

  // -------------------- 简易 Python 语法高亮 --------------------
  // 不依赖第三方库，纯正则匹配生成带 <span class="kw/fn/..."> 的 HTML
  function highlightPython(code) {
    if (!code) return '';
    // 先转义 HTML
    let html = escapeHtml(code);

    const KEYWORDS = [
      'def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'break',
      'continue', 'pass', 'import', 'from', 'as', 'try', 'except', 'finally',
      'raise', 'with', 'lambda', 'yield', 'global', 'nonlocal', 'in', 'not',
      'and', 'or', 'is', 'None', 'True', 'False', 'async', 'await',
    ];

    // 逐行处理 + 包成 <span> 让 CSS counter 渲染行号
    const lines = html.split('\n');
    const out = lines.map((raw) => {
      let line = raw;
      // 行内注释
      const hashIdx = line.indexOf('#');
      let tail = '';
      if (hashIdx !== -1) {
        tail = '<span class="cmt">' + line.substring(hashIdx) + '</span>';
        line = line.substring(0, hashIdx);
      }

      // 字符串
      line = line.replace(/("(?:[^"\\]|\\.)*")|('(?:[^'\\]|\\.)*')/g,
        (m) => '<span class="str">' + m + '</span>');

      // 数字
      line = line.replace(/\b(\d+\.?\d*)\b/g,
        '<span class="num">$1</span>');

      // 关键字
      const kwPattern = '\\b(' + KEYWORDS.join('|') + ')\\b';
      line = line.replace(new RegExp(kwPattern, 'g'),
        '<span class="kw">$1</span>');

      // 函数调用
      line = line.replace(/\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(\()/g,
        '<span class="fn">$1</span>$2');

      return '<span class="ln">' + line + tail + '</span>';
    });
    return out.join('');  // span 是 block，不需要换行符
  }

  // ==========================================================================
  // 启动
  // ==========================================================================
  init().catch((e) => {
    if (consoleEl) appendLog({ ts: nowText(), level: 'error', text: '初始化失败: ' + e.message });
    const runBtn = $('btn-run'); if (runBtn) runBtn.disabled = true;
  });
})();
