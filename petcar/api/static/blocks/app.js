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
      zoom: {
        controls: true, wheel: true, startScale: 0.9,
        maxScale: 2.0, minScale: 0.4,
      },
      trashcan: true,
      sounds: false,
      media: '/static/blocks/vendor/blockly/media/',
      move: { scrollbars: true, drag: true, wheel: true },
    });

    loadProgram();
    workspace.addChangeListener(onWorkspaceChange);
    bindButtons();
    setRunning(false);
    appendLog({ ts: nowText(), level: 'info', text: '积木编辑器已就绪' });
    pollStatus();
  }

  function nowText() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
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
    const starter = {
      blocks: {
        languageVersion: 0,
        blocks: [{
          type: 'event_start',
          id: 'start',
          x: 40,
          y: 40,
          next: {
            block: {
              type: 'move_for',
              id: 'move1',
              fields: { DIR: 'forward', SPEED: 150, SECONDS: 1 },
              next: {
                block: {
                  type: 'show_emotion',
                  id: 'emotion1',
                  fields: { EMOTION: 'happy' },
                },
              },
            },
          },
        }],
      },
    };
    Blockly.serialization.workspaces.load(starter, workspace);
  }

  function saveDraft() {
    if (!workspace) return;
    try {
      const program = Blockly.serialization.workspaces.save(workspace);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(program));
    } catch (e) {
      appendLog({ ts: nowText(), level: 'warn', text: '本地保存失败' });
    }
  }

  function onWorkspaceChange(event) {
    if (event && event.isUiEvent) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 500);
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
        if (data.errors && data.errors.length) {
          showErrors(data.errors);
        } else {
          appendLog({
            ts: nowText(), level: 'error',
            text: data.message || '运行失败',
          });
        }
        return;
      }
      currentRunId = data.run_id;
      lastLogId = 0;
      clearConsole();
      appendLog({
        ts: nowText(), level: 'info',
        text: `开始运行，共 ${data.blocks} 块积木`,
      });
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
      appendLog({
        ts: nowText(), level: estop ? 'warn' : 'info',
        text: estop ? '已发送急停' : '已发送停止',
      });
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
    clearTimeout(pollTimer);
    pollStatus();
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
    // 忽略上一次运行迟到的响应
    if (s.run_id > currentRunId) {
      currentRunId = s.run_id;
      lastLogId = 0;
    }
    if (s.run_id < currentRunId) return;

    const isRunning = s.state === 'running';
    if (isRunning !== running) setRunning(isRunning);

    const elapsed = $('elapsed');
    if (elapsed) {
      elapsed.textContent = isRunning
        ? `${Number(s.elapsed || 0).toFixed(1)}s`
        : '0.0s';
    }

    if (Array.isArray(s.logs)) {
      for (const item of s.logs) {
        if (item.id > lastLogId) {
          appendLog(item);
          lastLogId = item.id;
        }
      }
    }

    if (isRunning) {
      highlightBlock(s.current_block || null);
    } else {
      highlightBlock(null);
    }

    const sees = s.sees || {};
    setChip('see-face', !!sees.face);
    setChip('see-tennis', !!sees.tennis);
    setChip('see-color', !!sees.color);
  }

  // ==========================================================================
  // 高亮 / 错误
  // ==========================================================================
  function highlightBlock(id) {
    if (!workspace || id === lastBlockId) return;
    try {
      if (lastBlockId) workspace.highlightBlock(null);
    } catch (e) { /* ignore */ }
    lastBlockId = id;
    if (id) {
      try {
        workspace.highlightBlock(id);
      } catch (e) { /* ignore */ }
    }
  }

  function clearHighlight() {
    try {
      if (workspace && lastBlockId) workspace.highlightBlock(null);
    } catch (e) { /* ignore */ }
    lastBlockId = null;
  }

  function showErrors(errors) {
    errors.forEach((item) => {
      appendLog({
        ts: nowText(), level: 'error',
        text: item.message || '积木有误',
      });
      if (item.blockId && workspace) {
        try {
          workspace.centerOnBlock(item.blockId);
          highlightBlock(item.blockId);
        } catch (e) { /* ignore */ }
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
      t.className = 't';
      t.textContent = item.ts;
      row.appendChild(t);
    }
    row.appendChild(document.createTextNode(item.text || ''));
    consoleEl.appendChild(row);
    while (consoleEl.children.length > 300) {
      consoleEl.removeChild(consoleEl.firstChild);
    }
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function clearConsole() {
    if (consoleEl) consoleEl.innerHTML = '';
  }

  function setConnected(ok) {
    const el = $('conn');
    if (!el) return;
    el.textContent = ok ? '已连接' : '未连接';
    el.className = 'conn ' + (ok ? 'on' : 'off');
  }

  function setChip(id, on) {
    const el = $(id);
    if (el) el.classList.toggle('on', !!on);
  }

  // ==========================================================================
  // 按钮
  // ==========================================================================
  function bindButtons() {
    $('btn-run').addEventListener('click', runProgram);
    $('btn-stop').addEventListener('click', () => stopProgram(false));
    $('btn-estop').addEventListener('click', () => stopProgram(true));

    $('btn-new').addEventListener('click', () => {
      if (!confirm('新建会清空当前积木，确定吗？')) return;
      workspace.clear();
      localStorage.removeItem(STORAGE_KEY);
      loadStarter();
      clearConsole();
    });

    $('btn-export').addEventListener('click', () => {
      const program = Blockly.serialization.workspaces.save(workspace);
      const blob = new Blob([JSON.stringify(program, null, 2)], {
        type: 'application/json',
      });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'petcar-blocks.json';
      a.click();
      URL.revokeObjectURL(a.href);
    });

    $('btn-import').addEventListener('click', () => $('fileInput').click());
    $('fileInput').addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = '';
      if (!file) return;
      try {
        const text = await file.text();
        const program = JSON.parse(text);
        Blockly.serialization.workspaces.load(program, workspace);
        saveDraft();
        appendLog({ ts: nowText(), level: 'info', text: `已导入 ${file.name}` });
      } catch (err) {
        appendLog({ ts: nowText(), level: 'error', text: '导入失败: ' + err });
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        runProgram();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        stopProgram(false);
      }
    });

    window.addEventListener('beforeunload', saveDraft);
  }

  // ==========================================================================
  // 启动
  // ==========================================================================
  init().catch((e) => {
    if (consoleEl) {
      appendLog({ ts: nowText(), level: 'error', text: '初始化失败: ' + e.message });
    }
    const runBtn = $('btn-run');
    if (runBtn) runBtn.disabled = true;
  });
})();
