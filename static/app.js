/* ================= 局域网云盘 · 前端 ================= */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    view: 'browse',                 // browse | recent | image | video | audio | doc | notes | shares | settings
    path: '',
    crumbs: [{ name: '全部文件', path: '' }],
    items: [],
    sel: new Set(),
    mode: localStorage.getItem('landisk.mode') || 'grid',
    sort: localStorage.getItem('landisk.sort') || 'name',
    query: '',
    loading: false,
  };

  const TITLES = {
    recent: '最近使用', image: '图片', video: '视频', audio: '音乐', doc: '文档',
    notes: '笔记', shares: '我的分享', settings: '系统设置',
  };

  /* ---------------- 图标 ---------------- */
  const P = {
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="m4 17 4.5-4.5L13 17l3-3 4 4"/>',
    video: '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3"/>',
    audio: '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
    pdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 15h6"/>',
    text: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
    doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M8.5 12h7M8.5 15.5h7"/>',
    archive: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v7m-2.5-2.5L12 11l2.5-2.5"/><path d="M10 14h4v4h-4z"/>',
    markdown: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M6 15V9l2.5 3L11 9v6"/><path d="M16 9v4.5m0 0 2-2m-2 2-2-2"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9.5h18M3 15h18M9 4v16M15 4v16"/>',
    html: '<path d="M4 4h16v16H4z"/><path d="m9 9-2 3 2 3M15 9l2 3-2 3"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/>',
    word: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="m8.5 12 1 4.2 1.5-3 1.5 3 1-4.2"/>',
    excel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m9 9 6 6m0-6-6 6"/>',
    ppt: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/>',
    legacy: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 14h6"/>',
  };
  const icon = (kind) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${P[kind] || P.file}</svg>`;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ---------------- 通用 ---------------- */
  function fmtSize(n) {
    if (n === 0) return '0 B';
    if (!n && n !== 0) return '—';
    const u = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0, v = n;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (i === 0 ? v : v.toFixed(v >= 100 ? 0 : 1)) + ' ' + u[i];
  }
  function fmtTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000), now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const p = (x) => String(x).padStart(2, '0');
    if (sameDay) return `今天 ${p(d.getHours())}:${p(d.getMinutes())}`;
    if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}`;
    return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())}`;
  }
  function toast(msg, type = '') {
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    $('#toasts').appendChild(el);
    setTimeout(() => { el.style.transition = 'opacity .25s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 260); }, 2400);
  }

  async function api(url, opts = {}) {
    const res = await fetch(url, opts);
    if (res.status === 401) { showLogin(); throw new Error('请先登录'); }
    if (!res.ok) {
      let msg = res.statusText;
      try { const d = await res.json(); msg = d.detail || msg; } catch (_) { }
      throw new Error(msg);
    }
    return res.json();
  }
  const qs = (obj) => Object.entries(obj).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

  // 局域网一般是 http://192.168.x，不是安全上下文，navigator.clipboard 用不了，
  // 必须退回 textarea + execCommand 这条老路。
  async function copyText(text) {
    if (!text) return false;
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); return true; } catch (_) { /* 落到下面 */ }
    }
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:fixed;top:0;left:-9999px;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, ta.value.length);
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (_) { return false; }
  }

  /* ---------------- 主题 ---------------- */
  function initTheme() {
    const saved = localStorage.getItem('landisk.theme');
    const dark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  }
  $('#btnTheme').addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme;
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('landisk.theme', next);
  });

  /* ---------------- 渲染 ---------------- */
  function renderCrumbs() {
    const box = $('#crumbs');
    if (state.query) {
      box.innerHTML = `<span class="crumb current">搜索 “${esc(state.query)}”</span>`;
      return;
    }
    if (state.view !== 'browse') {
      box.innerHTML = `<span class="crumb current">${TITLES[state.view] || ''}</span>`;
      return;
    }
    box.innerHTML = state.crumbs.map((c, i) => {
      const last = i === state.crumbs.length - 1;
      return `${i ? '<span class="crumb-sep">/</span>' : ''}<button class="crumb ${last ? 'current' : ''}" data-path="${esc(c.path)}">${esc(c.name)}</button>`;
    }).join('');
    box.scrollLeft = box.scrollWidth;
  }

  function itemActions(it) {
    return `<div class="card-actions">
      <button data-act="share" title="分享链接"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/></svg></button>
      <button data-act="download" title="下载"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12m0 0 5-5m-5 5-5-5"/><path d="M4 20h16"/></svg></button>
      <button data-act="remark" title="备注"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8Z"/><path d="M8.5 10.5h7M8.5 13.5h4.5"/></svg></button>
      <button data-act="move" title="移动到…"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M12 11v5m0 0-2-2m2 2 2-2"/></svg></button>
      <button data-act="rename" title="重命名"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10-10-4-4L4 16Z"/></svg></button>
      <button data-act="delete" class="del" title="删除"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/></svg></button>
    </div>`;
  }

  const RMK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8Z"/></svg>';
  const rmkFlag = (it) => it.remark
    ? `<span class="rmk-flag" title="${esc(it.remark)}">${RMK_ICON}</span>` : '';

  function cardHTML(it) {
    const sel = state.sel.has(it.path);
    const thumb = it.kind === 'image'
      ? `<img src="/api/raw?${qs({ path: it.path })}" loading="lazy" alt="" draggable="false">`
      : icon(it.kind);
    return `<div class="card v-${it.kind} ${sel ? 'selected' : ''}" data-path="${esc(it.path)}" data-name="${esc(it.name)}" data-folder="${it.is_dir ? 1 : 0}" data-kind="${it.kind}" draggable="true">
      <button class="checkbox ${sel ? 'on' : ''}" data-act="select" title="选择"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12 5 5L20 6"/></svg></button>
      ${itemActions(it)}
      <div class="card-thumb">${thumb}</div>
      <div class="card-name" title="${esc(it.remark ? it.name + '\n— ' + it.remark : it.name)}">${esc(it.name)}${rmkFlag(it)}</div>
      <div class="card-meta"><span>${it.is_dir ? '文件夹' : fmtSize(it.size)}</span><span>·</span><span>${fmtTime(it.mtime)}</span></div>
    </div>`;
  }

  function rowHTML(it) {
    const sel = state.sel.has(it.path);
    const ico = it.kind === 'image'
      ? `<img src="/api/raw?${qs({ path: it.path })}" loading="lazy" alt="" draggable="false">`
      : icon(it.kind);
    return `<div class="row v-${it.kind} ${sel ? 'selected' : ''}" data-path="${esc(it.path)}" data-name="${esc(it.name)}" data-folder="${it.is_dir ? 1 : 0}" data-kind="${it.kind}" draggable="true">
      <button class="checkbox ${sel ? 'on' : ''}" data-act="select"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12 5 5L20 6"/></svg></button>
      <div class="row-icons">${ico}</div>
      <div class="row-name" title="${esc(it.remark ? it.name + '\n— ' + it.remark : it.name)}">${esc(it.name)}${rmkFlag(it)}</div>
      <div class="row-size">${it.is_dir ? '—' : fmtSize(it.size)}</div>
      <div class="row-time">${fmtTime(it.mtime)}</div>
      ${itemActions(it)}
    </div>`;
  }

  function render() {
    if (state.view === 'notes' || state.view === 'settings' || state.view === 'shares') return;
    const area = $('#filearea');
    const empty = $('#emptyState');
    area.className = 'filearea ' + state.mode;
    $('#viewToggle').querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.mode === state.mode));

    if (!state.items.length) {
      area.innerHTML = '';
      empty.classList.remove('hidden');
      $('#emptyTitle').textContent = state.query ? '没有找到匹配的文件' : '这里还没有文件';
      $('#emptyDesc').textContent = state.query ? '换个关键词试试' : '把文件拖进窗口，或点击右上角上传';
    } else {
      empty.classList.add('hidden');
      area.innerHTML = state.items.map(state.mode === 'grid' ? cardHTML : rowHTML).join('');
    }

    const total = state.items.reduce((s, i) => s + (i.is_dir ? 0 : i.size), 0);
    const folders = state.items.filter((i) => i.is_dir).length;
    $('#statusCount').textContent = state.items.length
      ? `${state.items.length} 个项目 · ${folders} 个文件夹 · ${fmtSize(total)}`
      : '空文件夹';
    $('#subbarLeft').textContent = state.query
      ? `在全部文件中搜索，命中 ${state.items.length} 项`
      : state.view === 'browse'
        ? `当前目录：${state.path || '根目录'}`
        : `${TITLES[state.view]} · 按修改时间排序`;
    updateSelBar();
  }

  function updateSelBar() {
    const bar = $('#selActions');
    if (state.sel.size) {
      bar.classList.remove('hidden');
      $('#selCount').textContent = `已选 ${state.sel.size} 项`;
    } else {
      bar.classList.add('hidden');
    }
  }

  /* ---------------- 数据 ---------------- */
  async function loadDir(path) {
    leaveNotesUI();
    leaveSettingsUI();
    leaveSharesUI();
    state.loading = true;
    $('#skeleton').classList.remove('hidden');
    try {
      const data = await api(`/api/list?${qs({ path: path || '', sort: state.sort })}`);
      state.view = 'browse';
      state.path = data.path || '';
      state.crumbs = data.crumbs;
      state.items = data.items;
      renderCrumbs();
      render();
      history.replaceState(null, '', state.path ? `#/${encodeURI(state.path)}` : '#/');
      syncNav();
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      state.loading = false;
      $('#skeleton').classList.add('hidden');
    }
  }

  async function loadBrowse(kind) {
    leaveNotesUI();
    leaveSettingsUI();
    leaveSharesUI();
    state.loading = true;
    $('#skeleton').classList.remove('hidden');
    try {
      const data = await api(`/api/browse?${qs({ kind })}`);
      state.view = kind;
      state.items = data.items;
      renderCrumbs();
      render();
      syncNav();
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      state.loading = false;
      $('#skeleton').classList.add('hidden');
    }
  }

  async function refresh() {
    state.sel.clear();
    if (state.view === 'notes') { await loadNotes(); return; }
    if (state.view === 'shares') { await loadShares(true); return; }
    if (state.view === 'settings') {
      if (setting.tab === 'logs') await loadLogs(true);
      else if (setting.tab === 'security') await loadSecurity();
      else await loadAbout(true);
      return;
    }
    if (state.query) {
      const data = await api(`/api/search?${qs({ q: state.query })}`);
      state.items = data.items;
      renderCrumbs();
      render();
    } else if (state.view === 'browse') {
      await loadDir(state.path);
    } else {
      await loadBrowse(state.view);
    }
    updateStats();
  }

  function syncNav() {
    $$('.nav-item').forEach((b) => {
      const v = b.dataset.view;
      if (state.view === 'notes') { b.classList.toggle('active', v === 'notes'); return; }
      if (state.view === 'settings') { b.classList.toggle('active', b.id === 'btnSettings'); return; }
      b.classList.toggle('active', !state.query && ((v === 'browse' && state.view === 'browse') || v === state.view));
    });
  }

  async function updateStats() {
    try {
      const s = await api('/api/stats');
      const used = s.disk_total - s.disk_free;
      const pct = Math.min(100, (used / s.disk_total) * 100);
      $('#storageBar').style.width = pct.toFixed(1) + '%';
      $('#storageText').textContent = `${fmtSize(used)} / ${fmtSize(s.disk_total)}`;
      $('#storageSub').textContent = `云盘占用 ${fmtSize(s.size)} · 剩余 ${fmtSize(s.disk_free)}`;
    } catch (_) { /* 忽略 */ }
  }

  /* ---------------- 交互 ---------------- */
  $('#filearea').addEventListener('click', async (e) => {
    const actBtn = e.target.closest('[data-act]');
    const el = e.target.closest('.card, .row');
    if (!el) return;
    const item = state.items.find((i) => i.path === el.dataset.path);
    if (!item) return;

    const act = actBtn && actBtn.dataset.act;
    if (act === 'select') { toggleSel(item.path, el); return; }
    if (act === 'share') { startShare([item.path], item.name); return; }
    if (act === 'remark') { openRemark(item); return; }
    if (act === 'download') { downloadItem(item); return; }
    if (act === 'move') { openMove([item.path], item.name); return; }
    if (act === 'rename') { doRename(item); return; }
    if (act === 'delete') { doDelete([item.path], item.name); return; }

    if (item.is_dir) {
      state.query = '';
      $('#searchInput').value = '';
      $('#searchClear').classList.add('hidden');
      loadDir(item.path);
    } else {
      openPreview(item);
    }
  });

  function toggleSel(path, el) {
    if (state.sel.has(path)) state.sel.delete(path); else state.sel.add(path);
    const on = state.sel.has(path);
    el.classList.toggle('selected', on);
    const cb = el.querySelector('.checkbox');
    if (cb) cb.classList.toggle('on', on);
    updateSelBar();
  }

  $('#crumbs').addEventListener('click', (e) => {
    const b = e.target.closest('.crumb');
    if (!b || !b.dataset.path) return;
    if (state.query) { clearSearch(); return; }
    state.query = '';
    loadDir(b.dataset.path);
  });

  $$('.nav-item[data-view]').forEach((b) => b.addEventListener('click', () => {
    const v = b.dataset.view;
    state.query = '';
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    $('#sidebar').classList.remove('open');
    if (v === 'notes') { enterNotes(); return; }
    if (v === 'shares') { enterShares(); return; }
    if (v === 'browse') loadDir(''); else loadBrowse(v);
  }));

  $('#viewToggle').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mode]');
    if (!b) return;
    state.mode = b.dataset.mode;
    localStorage.setItem('landisk.mode', state.mode);
    render();
  });

  $('#sortSelect').addEventListener('change', (e) => {
    state.sort = e.target.value;
    localStorage.setItem('landisk.sort', state.sort);
    if (state.view === 'browse' && !state.query) loadDir(state.path);
  });

  let searchTimer;
  $('#searchInput').addEventListener('input', (e) => {
    const v = e.target.value.trim();
    $('#searchClear').classList.toggle('hidden', !v);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      state.query = v;
      if (state.view === 'notes') {
        renderCrumbs();
        await loadNotes();
        return;
      }
      if (!v) { clearSearch(); return; }
      state.sel.clear();
      const data = await api(`/api/search?${qs({ q: v })}`);
      state.items = data.items;
      renderCrumbs();
      render();
    }, 280);
  });
  $('#searchClear').addEventListener('click', clearSearch);
  function clearSearch() {
    state.query = '';
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    if (state.view === 'notes') { renderCrumbs(); loadNotes(); return; }
    refresh();
  }

  /* ---------------- 上传 ---------------- */
  $('#btnUploadMain').addEventListener('click', () => {
    if (state.view === 'notes') { newNote(); return; }
    pickFiles();
  });
  $('#btnUploadSm').addEventListener('click', pickFiles);
  function pickFiles() { if (state.query) { toast('请先退出搜索再上传'); return; } $('#filePicker').click(); }
  $('#filePicker').addEventListener('change', (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = '';
    if (files.length) uploadFiles(files, state.view === 'browse' ? state.path : '');
  });

  function upItem(name) {
    $('#uploadPanel').classList.remove('hidden');
    const el = document.createElement('div');
    el.className = 'up-item';
    el.innerHTML = `<div class="up-top"><span class="up-name"></span><span class="up-pct">等待中</span></div><div class="up-bar"><i></i></div>`;
    $('.up-name', el).textContent = name;
    $('#uploadList').prepend(el);
    return el;
  }

  async function uploadFiles(files, destPath) {
    let done = 0;
    $('#uploadTitle').textContent = `正在上传 ${files.length} 个文件`;
    for (const f of files) {
      const el = upItem(f.name);
      const bar = $('.up-bar i', el);
      const pct = $('.up-pct', el);
      try {
        await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/api/upload');
          xhr.upload.addEventListener('progress', (ev) => {
            if (!ev.lengthComputable) return;
            const p = Math.round((ev.loaded / ev.total) * 100);
            bar.style.width = p + '%';
            pct.textContent = p + '%';
          });
          xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) resolve();
            else {
              let msg = '上传失败';
              try { msg = JSON.parse(xhr.responseText).detail || msg; } catch (_) { }
              reject(new Error(msg));
            }
          });
          xhr.addEventListener('error', () => reject(new Error('网络错误')));
          const fd = new FormData();
          fd.append('path', destPath || '');
          fd.append('files', f, f.name);
          xhr.send(fd);
        });
        el.classList.add('done');
        bar.style.width = '100%';
        pct.textContent = '完成';
        done++;
      } catch (err) {
        el.classList.add('err');
        pct.textContent = '失败';
        toast(`${f.name}：${err.message}`, 'err');
      }
    }
    if (done) toast(`已上传 ${done} 个文件`);
    $('#uploadTitle').textContent = done === files.length ? '上传完成' : '部分文件上传失败';
    setTimeout(() => $('#uploadPanel').classList.add('hidden'), 4000);
    if (!state.query && (state.view !== 'browse' || state.path === destPath)) refresh();
    else updateStats();
  }

  $('#uploadClose').addEventListener('click', () => $('#uploadPanel').classList.add('hidden'));

  /* 拖拽 */
  let dragDepth = 0;
  let dragPath = '';
  const hasFiles = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
  window.addEventListener('dragenter', (e) => {
    if (!hasFiles(e)) return;
    dragDepth++;
    $('#dropText').textContent = state.view === 'notes' ? '松手插入图片到笔记' : '松手上传到当前目录';
    $('#dropMask').classList.add('show');
  });
  window.addEventListener('dragover', (e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
  window.addEventListener('dragleave', (e) => {
    if (!hasFiles(e)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) $('#dropMask').classList.remove('show');
  });
  $('#filearea').addEventListener('dragstart', (e) => {
    const el = e.target.closest('.card, .row');
    if (!el || !e.dataTransfer) return;
    dragPath = el.dataset.path;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragPath);
    el.classList.add('dragging');
  });
  $('#filearea').addEventListener('dragend', () => {
    dragPath = '';
    $$('.dragging').forEach((el) => el.classList.remove('dragging'));
    $$('.drop-target').forEach((el) => el.classList.remove('drop-target'));
    $('#dropText').textContent = '松手上传到当前目录';
  });
  $('#filearea').addEventListener('dragover', (e) => {
    const f = e.target.closest('[data-folder="1"]');
    $$('.drop-target').forEach((el) => el.classList.remove('drop-target'));
    if (f) f.classList.add('drop-target');
    if (dragPath && f) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      $('#dropText').textContent = `松手移动到「${f.dataset.name}」`;
      return;
    }
    if (!dragPath) $('#dropText').textContent = f ? `松手上传到「${f.dataset.name}」` : '松手上传到当前目录';
  });
  // 拖到文件夹卡片上 => 移动
  $('#filearea').addEventListener('drop', (e) => {
    if (!dragPath) return;
    e.preventDefault();
    e.stopPropagation();
    const folder = e.target.closest('[data-folder="1"]');
    const moving = dragPath;
    dragPath = '';
    $$('.drop-target').forEach((el) => el.classList.remove('drop-target'));
    $$('.dragging').forEach((el) => el.classList.remove('dragging'));
    if (folder) doMove([moving], folder.dataset.path, folder.dataset.name);
  });
  window.addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    $('#dropMask').classList.remove('show');
    $$('.drop-target').forEach((el) => el.classList.remove('drop-target'));
    const files = Array.from(e.dataTransfer.files || []);
    if (state.view === 'notes') {
      const imgs = files.filter((f) => /^image\//.test(f.type));
      if (imgs.length) imgs.forEach(uploadNoteImage);
      else toast('笔记里只能插入图片', 'err');
      $('#dropText').textContent = '松手上传到当前目录';
      return;
    }
    const folder = e.target.closest && e.target.closest('[data-folder="1"]');
    const dest = folder ? folder.dataset.path : (state.view === 'browse' && !state.query ? state.path : '');
    if (files.length) uploadFiles(files, dest);
    $('#dropText').textContent = '松手上传到当前目录';
  });

  /* ---------------- 对话框 ---------------- */
  // 只把弹窗设成 display:none 不会让 <video>/<audio> 停下，
  // 所以关闭前必须显式 pause + 释放 src，断开已经缓冲的请求。
  function stopMedia(root) {
    if (!root) return;
    root.querySelectorAll('audio, video').forEach((m) => {
      try {
        m.pause();
        m.currentTime = 0;
        m.removeAttribute('src');
        m.load();   // 中止后面的 Range 请求，避免继续跑流量
      } catch (_) { /* 元素已被移除就忽略 */ }
    });
  }

  function hideModal(el) {
    if (!el) return;
    stopMedia(el);
    el.classList.add('hidden');
  }

  function openModal(id) { $(id).classList.remove('hidden'); }
  function closeModal(id) { hideModal($(id)); }
  $$('[data-close]').forEach((el) => el.addEventListener('click', () => hideModal(el.closest('.modal'))));

  function askText({ title, value = '', placeholder = '' }) {
    return new Promise((resolve) => {
      const modal = $('#promptModal');
      $('#promptTitle').textContent = title;
      const input = $('#promptInput');
      input.value = value;
      input.placeholder = placeholder;
      openModal('#promptModal');
      setTimeout(() => { input.focus(); input.select(); }, 30);
      const form = $('#promptForm');
      const onSubmit = (e) => {
        e.preventDefault();
        cleanup();
        resolve(input.value.trim() || null);
      };
      const onClose = () => { cleanup(); resolve(null); };
      function cleanup() {
        form.removeEventListener('submit', onSubmit);
        modal.querySelectorAll('[data-close]').forEach((b) => b.removeEventListener('click', onClose));
        closeModal('#promptModal');
      }
      form.addEventListener('submit', onSubmit);
      modal.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', onClose));
    });
  }

  function askConfirm({ title, text, okText = '删除' }) {
    return new Promise((resolve) => {
      const modal = $('#confirmModal');
      $('#confirmTitle').textContent = title;
      $('#confirmText').textContent = text;
      const ok = $('#confirmOk');
      ok.textContent = okText;
      openModal('#confirmModal');
      const onOk = () => { cleanup(); resolve(true); };
      const onClose = () => { cleanup(); resolve(false); };
      function cleanup() {
        ok.removeEventListener('click', onOk);
        modal.querySelectorAll('[data-close]').forEach((b) => b.removeEventListener('click', onClose));
        closeModal('#confirmModal');
      }
      ok.addEventListener('click', onOk);
      modal.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', onClose));
    });
  }

  /* ---------------- 文件操作 ---------------- */
  /* ---------------- 移动到文件夹 ---------------- */
  let movePaths = [];
  let moveTarget = '';

  function treeHTML(nodes, depth) {
    return nodes.map((n) => `
      <div class="tree-row" data-path="${esc(n.path)}" style="padding-left:${8 + depth * 16}px">
        ${icon('folder')}<span>${esc(n.name)}</span>
      </div>
      ${n.children && n.children.length ? treeHTML(n.children, depth + 1) : ''}`).join('');
  }

  async function openMove(paths, label) {
    if (!paths.length) return;
    movePaths = paths;
    moveTarget = '';
    $('#moveSub').textContent = paths.length === 1
      ? `将「${label}」移动到：`
      : `将 ${paths.length} 个项目移动到：`;
    $('#moveDest').textContent = '全部文件（根目录）';
    openModal('#moveModal');
    $('#moveTree').innerHTML = '<div class="tree-note">加载中…</div>';
    try {
      const data = await api('/api/tree');
      $('#moveTree').innerHTML = `<div class="tree-row active" data-path="" style="padding-left:8px">${icon('folder')}<span>全部文件（根目录）</span></div>`
        + treeHTML(data.children || [], 1)
        + (data.truncated ? '<div class="tree-note">文件夹较多，仅显示前 500 个</div>' : '');
    } catch (e) {
      $('#moveTree').innerHTML = `<div class="tree-note">${esc(e.message)}</div>`;
    }
  }

  async function doMove(paths, dest, label) {
    try {
      const r = await api('/api/move', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths, dest }),
      });
      if (r.items.length) toast(`已移动 ${r.items.length} 项到「${label || '根目录'}」`);
      else toast('未移动：已在该位置，或目标在自身内部', 'err');
      state.sel.clear();
      refresh();
    } catch (e) { toast(e.message, 'err'); }
  }

  $('#moveTree').addEventListener('click', (e) => {
    const row = e.target.closest('.tree-row');
    if (!row) return;
    $$('#moveTree .tree-row').forEach((r) => r.classList.remove('active'));
    row.classList.add('active');
    moveTarget = row.dataset.path;
    $('#moveDest').textContent = moveTarget || '全部文件（根目录）';
  });

  $('#moveOk').addEventListener('click', async () => {
    if (!movePaths.length) return;
    const label = $('#moveDest').textContent;
    const paths = movePaths.slice();
    movePaths = [];
    closeModal('#moveModal');
    await doMove(paths, moveTarget, label);
  });

  /* ---------------- 文件备注 ---------------- */
  let remarkTarget = null;

  function openRemark(item) {
    remarkTarget = item;
    $('#remarkName').textContent = item.name;
    $('#remarkText').value = item.remark || '';
    openModal('#remarkModal');
    setTimeout(() => $('#remarkText').focus(), 30);
  }

  async function saveRemark(text) {
    if (!remarkTarget) return;
    try {
      await api('/api/remarks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: remarkTarget.path, text }),
      });
      closeModal('#remarkModal');
      toast(text ? '备注已保存' : '已清除备注');
      remarkTarget = null;
      refresh();
    } catch (e) { toast(e.message, 'err'); }
  }

  $('#remarkSave').addEventListener('click', () => saveRemark($('#remarkText').value));
  $('#remarkClear').addEventListener('click', () => saveRemark(''));

  async function doRename(item) {
    const name = await askText({ title: '重命名', value: item.name });
    if (!name || name === item.name) return;
    try {
      await api('/api/rename', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: item.path, new_name: name }),
      });
      toast('已重命名');
      refresh();
    } catch (e) { toast(e.message, 'err'); }
  }

  async function doDelete(paths, label) {
    const ok = await askConfirm({
      title: paths.length > 1 ? `删除 ${paths.length} 个项目？` : '删除文件？',
      text: `「${label}」删除后无法恢复。`,
    });
    if (!ok) return;
    try {
      const r = await api('/api/delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths }),
      });
      toast(`已删除 ${r.removed} 项`);
      state.sel.clear();
      refresh();
    } catch (e) { toast(e.message, 'err'); }
  }

  function downloadItem(item) {
    const url = item.is_dir
      ? `/api/zip?${qs({ path: item.path })}`
      : `/api/download?${qs({ path: item.path })}`;
    triggerDownload(url);
  }
  function triggerDownload(url) {
    const a = document.createElement('a');
    a.href = url;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function newFolder() {
    if (state.query) { toast('请先退出搜索'); return; }
    const name = await askText({ title: '新建文件夹', placeholder: '文件夹名称' });
    if (!name) return;
    try {
      await api('/api/mkdir', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: state.view === 'browse' ? state.path : '', name }),
      });
      toast('文件夹已创建');
      refresh();
    } catch (e) { toast(e.message, 'err'); }
  }
  $('#btnNewFolder').addEventListener('click', newFolder);
  $('#btnNewFolderM').addEventListener('click', () => {
    $('#sidebar').classList.remove('open');
    newFolder();
  });

  $('#selClear').addEventListener('click', () => {
    state.sel.clear();
    $$('.selected').forEach((el) => el.classList.remove('selected'));
    $$('.checkbox.on').forEach((el) => el.classList.remove('on'));
    updateSelBar();
  });
  $('#selDelete').addEventListener('click', () => {
    const paths = Array.from(state.sel);
    doDelete(paths, paths.length === 1 ? (paths[0].split('/').pop() || '该项目') : `${paths.length} 个项目`);
  });
  $('#selMove').addEventListener('click', () => {
    const paths = Array.from(state.sel);
    if (!paths.length) return;
    const label = paths.length === 1 ? paths[0].split('/').pop() : `${paths.length} 个项目`;
    openMove(paths, label);
  });
  $('#selDownload').addEventListener('click', async () => {
    const paths = Array.from(state.sel);
    if (paths.length === 1) {
      const it = state.items.find((i) => i.path === paths[0]);
      if (it) return downloadItem(it);
    }
    try {
      toast('正在打包，请稍候…');
      const res = await fetch('/api/zip_many', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths }),
      });
      if (!res.ok) throw new Error('打包失败');
      const blob = await res.blob();
      const cd = res.headers.get('content-disposition') || '';
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
      const name = m ? decodeURIComponent(m[1]) : 'download.zip';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) { toast(e.message, 'err'); }
  });

  /* ---------------- 预览 ---------------- */
  let editing = false;
  let previewItem = null;
  let previewSource = '';
  const EDITABLE = ['text', 'markdown', 'html', 'table'];

  const encodePath = (p) => p.split('/').map(encodeURIComponent).join('/');

  // md 里的相对图片路径 -> 云盘真实路径
  function assetUrl(src, basePath) {
    if (!src) return '';
    if (/^(https?:|data:|mailto:|#|\/)/i.test(src)) return src;
    let clean = src;
    try { clean = decodeURI(src); } catch (_) { }
    const dir = basePath.includes('/') ? basePath.slice(0, basePath.lastIndexOf('/')) : '';
    const stack = dir ? dir.split('/') : [];
    for (const part of clean.split('/')) {
      if (!part || part === '.') continue;
      if (part === '..') { stack.pop(); continue; }
      stack.push(part);
    }
    return '/files/' + stack.map(encodeURIComponent).join('/');
  }

  function mdInline(text, base) {
    const codes = [];
    let s = esc(text);
    s = s.replace(/`([^`]+)`/g, (_m, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0002`; });
    s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_m, alt, src) =>
      `<img src="${esc(assetUrl(src, base))}" alt="${alt}" loading="lazy">`);
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, label, href) => {
      const h = assetUrl(href, base);
      const safe = /^(javascript|vbscript|data):/i.test(h) ? '#' : h;
      return `<a href="${esc(safe)}" target="_blank" rel="noopener">${label}</a>`;
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    s = s.replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>');
    s = s.replace(/\u0001(\d+)\u0002/g, (_m, n) => `<code>${codes[+n]}</code>`);
    return s;
  }

  function mdToHtml(src, base) {
    const lines = src.replace(/\r\n?/g, '\n').split('\n');
    const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
    let html = '';
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      const fence = line.match(/^\s*(```|~~~)/);
      if (fence) {
        const marker = fence[1];
        const buf = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(marker)) { buf.push(lines[i]); i++; }
        i++;
        html += `<pre class="md-code"><code>${esc(buf.join('\n'))}</code></pre>`;
        continue;
      }

      if (!line.trim()) { i++; continue; }

      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        const lv = h[1].length;
        html += `<h${lv}>${mdInline(h[2], base)}</h${lv}>`;
        i++;
        continue;
      }

      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { html += '<hr>'; i++; continue; }

      if (/^\s*>/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          buf.push(lines[i].replace(/^\s*>\s?/, ''));
          i++;
        }
        html += `<blockquote>${mdToHtml(buf.join('\n'), base)}</blockquote>`;
        continue;
      }

      if (/\|/.test(line) && i + 1 < lines.length && /^[\s|:-]+$/.test(lines[i + 1]) && /-/.test(lines[i + 1])) {
        const head = cells(line);
        const aligns = cells(lines[i + 1]).map((a) =>
          a.startsWith(':') && a.endsWith(':') ? 'center' : a.endsWith(':') ? 'right' : a.startsWith(':') ? 'left' : '');
        const rows = [];
        i += 2;
        while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(cells(lines[i])); i++; }
        const align = (k) => (aligns[k] ? ` style="text-align:${aligns[k]}"` : '');
        html += '<div class="md-table"><table><thead><tr>'
          + head.map((c, k) => `<th${align(k)}>${mdInline(c, base)}</th>`).join('')
          + '</tr></thead><tbody>'
          + rows.map((r) => '<tr>' + head.map((_c, k) => `<td${align(k)}>${mdInline(r[k] || '', base)}</td>`).join('') + '</tr>').join('')
          + '</tbody></table></div>';
        continue;
      }

      if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
        const ordered = /^\s*\d/.test(line);
        const items = [];
        while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*([-*+]|\d+[.)])\s+/, ''));
          i++;
        }
        const tag = ordered ? 'ol' : 'ul';
        html += `<${tag}>` + items.map((t) => {
          const task = t.match(/^\[([ xX])\]\s+(.*)$/);
          if (task) {
            return `<li class="md-task"><input type="checkbox" disabled ${task[1].toLowerCase() === 'x' ? 'checked' : ''}> ${mdInline(task[2], base)}</li>`;
          }
          return `<li>${mdInline(t, base)}</li>`;
        }).join('') + `</${tag}>`;
        continue;
      }

      const buf = [];
      while (
        i < lines.length && lines[i].trim()
        && !/^\s*(#{1,6}\s|>|```|~~~|[-*+]\s|\d+[.)]\s)/.test(lines[i])
        && !/^\s*([-*_])(\s*\1){2,}\s*$/.test(lines[i])
      ) { buf.push(lines[i]); i++; }
      if (!buf.length) { i++; continue; }
      html += `<p>${mdInline(buf.join('\n'), base).replace(/\n/g, '<br>')}</p>`;
    }
    return html;
  }

  function sniffDelim(text) {
    const first = (text.split(/\r?\n/, 1)[0] || '');
    const score = [
      [',', (first.match(/,/g) || []).length],
      ['\t', (first.match(/\t/g) || []).length],
      [';', (first.match(/;/g) || []).length],
    ].sort((a, b) => b[1] - a[1]);
    return score[0][1] > 0 ? score[0][0] : ',';
  }

  function parseDelimited(text, delim) {
    const rows = [];
    let row = [];
    let cell = '';
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
        } else cell += c;
      } else if (c === '"') {
        quoted = true;
      } else if (c === delim) {
        row.push(cell); cell = '';
      } else if (c === '\n') {
        row.push(cell); rows.push(row); row = []; cell = '';
      } else if (c !== '\r') {
        cell += c;
      }
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }

  function tableHTML(rows) {
    if (!rows.length) return '<div class="preview-fallback"><p>空表格</p></div>';
    const MAX_ROWS = 500;
    const MAX_COLS = 30;
    const head = rows[0].slice(0, MAX_COLS);
    const body = rows.slice(1, MAX_ROWS + 1);
    const truncated = rows.length - 1 > MAX_ROWS;
    return `<div class="csv-wrap"><table class="csv-table">
      <thead><tr><th class="csv-idx"></th>${head.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead>
      <tbody>${body.map((r, k) => `<tr><td class="csv-idx">${k + 1}</td>${head.map((_c, j) => {
        const v = r[j] === undefined ? '' : r[j];
        const num = v !== '' && /^-?\d+(\.\d+)?$/.test(v.trim());
        return `<td${num ? ' class="num"' : ''}>${esc(v)}</td>`;
      }).join('')}</tr>`).join('')}</tbody>
    </table></div>
    <div class="csv-note">${rows.length - 1} 行 · ${rows[0].length} 列${truncated ? ` · 仅显示前 ${MAX_ROWS} 行` : ''}${rows[0].length > MAX_COLS ? ` · 仅显示前 ${MAX_COLS} 列` : ''}</div>`;
  }

  /* ---------------- Office 预览（Word / Excel / PPT） ---------------- */
  const OFFICE_KINDS = ['word', 'excel', 'ppt', 'legacy'];

  function docFontSize(sz) {
    // Word 里 11pt 约等于正文，换算成 em，限制在合理区间
    return Math.min(2.6, Math.max(0.72, sz / 11));
  }

  function runsHTML(runs, om) {
    return (runs || []).map((r) => {
      if (r.img) {
        return `<img class="doc-inline-img" src="${om(r.img)}" alt="" loading="lazy" onerror="this.style.display='none'">`;
      }
      if (!r.t) return '';
      let t = esc(r.t).replace(/\n/g, '<br>');
      if (r.b) t = `<strong>${t}</strong>`;
      if (r.i) t = `<em>${t}</em>`;
      if (r.u) t = `<u>${t}</u>`;
      if (r.s) t = `<s>${t}</s>`;
      if (r.c) t = `<span style="color:${esc(r.c)}">${t}</span>`;
      if (r.sz) t = `<span style="font-size:${docFontSize(r.sz)}em">${t}</span>`;
      if (r.href) t = `<a href="${esc(r.href)}" target="_blank" rel="noopener noreferrer">${t}</a>`;
      return t;
    }).join('');
  }

  function docTableHTML(b, om) {
    return `<table class="doc-table">${b.rows.map((row) => `<tr>${row.map((c) => {
      const span = c.colspan > 1 ? ` colspan="${c.colspan}"` : '';
      const body = (c.blocks && c.blocks.length)
        ? c.blocks.map((bl) => bl.t === 'table' ? '' : runsHTML(bl.runs, om)).join('<br>')
        : esc(c.text || '').replace(/\n/g, '<br>');
      return `<td${span}${c.head ? ' class="head"' : ''}>${body}</td>`;
    }).join('')}</tr>`).join('')}</table>`;
  }

  function wordHTML(data, om) {
    const out = [];
    let list = null;
    const flush = () => {
      if (!list) return;
      const tag = list.ordered ? 'ol' : 'ul';
      out.push(`<${tag} class="doc-list">${list.items.join('')}</${tag}>`);
      list = null;
    };

    for (const b of data.blocks) {
      if (b.t === 'li') {
        if (list && list.ordered !== b.ordered) flush();
        if (!list) list = { ordered: !!b.ordered, items: [] };
        list.items.push(`<li style="margin-left:${Math.min(b.level || 0, 5) * 1.5}em">${runsHTML(b.runs, om)}</li>`);
        continue;
      }
      flush();
      if (b.t === 'table') { out.push(docTableHTML(b, om)); continue; }
      if (b.t === 'img') {
        out.push(`<figure class="doc-figure"><img src="${om(b.src)}" alt="" loading="lazy" onerror="this.parentNode.style.display='none'"></figure>`);
        continue;
      }
      const txt = runsHTML(b.runs, om);
      if (!txt.trim()) continue;
      const align = b.align && b.align !== 'left' ? ` style="text-align:${esc(b.align)}"` : '';
      if (b.style && /^h[1-6]$/.test(b.style)) {
        const lv = b.style[1];
        out.push(`<h${lv} class="doc-h${lv}"${align}>${txt}</h${lv}>`);
      } else if (b.style === 'quote') {
        out.push(`<blockquote${align}>${txt}</blockquote>`);
      } else if (b.style === 'code') {
        out.push(`<pre class="doc-code">${txt}</pre>`);
      } else {
        out.push(`<p${align}>${txt}</p>`);
      }
    }
    flush();
    return `<div class="doc-scroll word-scroll"><article class="doc-page">${out.join('') || '<p class="doc-empty">（文档里没有可显示的正文）</p>'}</article></div>`;
  }

  /* ---- Excel ---- */
  let xlsxState = null;

  function sheetTableHTML(s) {
    if (!s.rows.length) return '<div class="preview-fallback"><p>这张表是空的</p></div>';
    const limit = 2000;
    const rows = s.rows.slice(0, limit);
    const cell = (c) => {
      if (c === null) return '<td></td>';
      if (c.skip) return '';
      const attrs = [
        c.rs > 1 ? ` rowspan="${c.rs}"` : '',
        c.cs > 1 ? ` colspan="${c.cs}"` : '',
        c.a && c.a !== 'left' ? ` class="a-${c.a}"` : '',
      ].join('');
      return `<td${attrs}>${esc(c.v)}</td>`;
    };
    return `<table class="xlsx-table">
      <thead><tr><th class="xlsx-corner"></th>${s.cols.map((c) => `<th class="xlsx-col">${c}</th>`).join('')}</tr></thead>
      <tbody>${rows.map((row, i) => `<tr><th class="xlsx-row">${i + 1}</th>${row.map(cell).join('')}</tr>`).join('')}</tbody>
    </table>
    ${rows.length < s.rows.length || s.truncated ? `<div class="xlsx-more">只显示前 ${rows.length} 行，完整内容请下载查看</div>` : ''}`;
  }

  function xlsxShell(data) {
    xlsxState = { data, tab: 0 };
    const multi = data.sheets.length > 1;
    return `<div class="xlsx-wrap">
      ${multi ? `<div class="sheet-tabs">${data.sheets.map((s, i) => `<button class="sheet-tab${i === 0 ? ' active' : ''}" data-sheet="${i}">${esc(s.name)}</button>`).join('')}</div>` : ''}
      <div class="xlsx-scroll" id="xlsxScroll">${sheetTableHTML(data.sheets[0])}</div>
      <div class="csv-note" id="xlsxNote"></div>
    </div>`;
  }

  function paintSheet(idx) {
    if (!xlsxState) return;
    const s = xlsxState.data.sheets[idx];
    if (!s) return;
    xlsxState.tab = idx;
    const scroll = $('#xlsxScroll');
    if (scroll) { scroll.innerHTML = sheetTableHTML(s); scroll.scrollTop = 0; scroll.scrollLeft = 0; }
    $$('.sheet-tab').forEach((b) => b.classList.toggle('active', +b.dataset.sheet === idx));
    const note = $('#xlsxNote');
    if (note) {
      const filled = s.rows.filter((r) => r.some((c) => c && !c.skip && c.v !== '')).length;
      note.textContent = `工作表「${s.name}」 · ${filled} 行有数据 · ${s.cols.length} 列${xlsxState.data.sheets.length > 1 ? ` · 共 ${xlsxState.data.sheets.length} 张表` : ''}`;
    }
  }

  /* ---- PPT ---- */
  function isDark(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return false;
    const n = parseInt(m[1], 16);
    const r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255;
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140;
  }

  function pptRuns(runs) {
    return (runs || []).map((r) => {
      if (!r.t) return '';
      let t = esc(r.t).replace(/\n/g, '<br>');
      if (r.b) t = `<strong>${t}</strong>`;
      if (r.i) t = `<em>${t}</em>`;
      if (r.c) t = `<span style="color:${esc(r.c)}">${t}</span>`;
      return t;
    }).join('');
  }

  function pptLine(line) {
    const lvl = Math.min(line.lvl || 0, 4);
    return `<div class="pptx-line" style="padding-left:${lvl * 1.6}em">${lvl > 0 ? '<span class="pptx-bullet">◦</span>' : '<span class="pptx-bullet">•</span>'}${pptRuns(line.runs)}</div>`;
  }

  function pptSlideHTML(s, om) {
    const dark = isDark(s.bg);
    const bg = s.bg ? `background:${esc(s.bg)};` : '';
    const inner = [];
    for (const b of s.blocks) {
      if (b.type === 'title') {
        inner.push(`<h2 class="pptx-title">${b.lines.map((l) => pptRuns(l.runs)).join('<br>')}</h2>`);
      } else if (b.type === 'body') {
        inner.push(`<div class="pptx-body">${b.lines.map(pptLine).join('')}</div>`);
      } else if (b.type === 'pic') {
        inner.push(`<div class="pptx-pic"><img src="${om(b.src)}" alt="" loading="lazy" onerror="this.parentNode.style.display='none'"></div>`);
      } else if (b.type === 'table') {
        const rows = b.table.rows.map((r) => `<tr>${r.map((c) => `<td${c.colspan > 1 ? ` colspan="${c.colspan}"` : ''}>${esc(c.text)}</td>`).join('')}</tr>`).join('');
        inner.push(`<table class="pptx-table">${rows}</table>`);
      }
    }
    if (!inner.length) inner.push('<div class="pptx-body pptx-blank">（这一页没有文字内容）</div>');
    return `<div class="slide-card">
      <div class="slide-inner ${dark ? 'on-dark' : ''}" style="${bg}">${inner.join('')}</div>
      <div class="slide-num">${s.index}</div>
    </div>`;
  }

  function pptShell(data, om) {
    return `<div class="doc-scroll pptx-scroll">${data.slides.map((s) => pptSlideHTML(s, om)).join('')}
      ${data.truncated ? '<div class="pptx-more">幻灯片较多，只显示前 200 页</div>' : ''}</div>`;
  }

  async function renderOffice(item, body) {
    if (item.kind === 'legacy') {
      body.innerHTML = fallbackHTML(item, '这是 Office 97-2003 的老格式（.doc/.xls/.ppt），浏览器端无法解析。用 Office 或 WPS 另存为 .docx/.xlsx/.pptx 后即可在线预览，或直接下载。');
      return;
    }
    try {
      const d = await api(`/api/office?${qs({ path: item.path })}`);
      if (!d || d.type === 'error') throw new Error((d && d.message) || '解析失败');
      const om = (name) => `/api/office_media?${qs({ path: item.path, name })}`;
      body.classList.add('doc-mode');
      if (d.type === 'word') {
        body.innerHTML = wordHTML(d, om);
      } else if (d.type === 'excel') {
        body.innerHTML = xlsxShell(d);
        paintSheet(0);
      } else if (d.type === 'ppt') {
        body.innerHTML = pptShell(d, om);
      } else {
        throw new Error('未知的文档类型');
      }
    } catch (e) {
      body.classList.remove('doc-mode');
      body.innerHTML = fallbackHTML(item, e.message || '无法解析该文档');
    }
  }

  /* ---- 音频播放器 ---- */
  function fmtClock(sec) {
    if (!isFinite(sec) || sec < 0) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  async function renderAudio(item, body) {
    const raw = `/api/raw?${qs({ path: item.path })}`;
    const base = item.name.replace(/\.[^.]+$/, '');
    body.classList.add('doc-mode');
    body.innerHTML = `<div class="audio-wrap">
      <div class="audio-card">
        <div class="audio-cover" id="audioCover"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/></svg></div>
        <div class="audio-info">
          <div class="audio-title" id="audioTitle">${esc(base)}</div>
          <div class="audio-artist" id="audioArtist"></div>
          <div class="audio-meta" id="audioMeta">${esc(item.ext.toUpperCase())} · ${fmtSize(item.size)}</div>
        </div>
      </div>
      <audio class="audio-el" id="audioEl" src="${raw}" controls autoplay preload="metadata"></audio>
      <div class="audio-tip" id="audioTip"></div>
    </div>`;

    const el = $('#audioEl');
    const tip = $('#audioTip');
    if (el) {
      el.addEventListener('error', () => {
        if (tip) { tip.textContent = '这个音频浏览器可能不支持该编码，建议下载后播放'; tip.classList.add('err'); }
      });
    }

    try {
      const m = await api(`/api/audio_meta?${qs({ path: item.path })}`);
      if ($('#audioTitle')) $('#audioTitle').textContent = m.title || base;
      const sub = [m.artist, m.album].filter(Boolean).join(' · ');
      if ($('#audioArtist')) $('#audioArtist').textContent = sub || '未知艺人';
      if ($('#audioMeta')) {
        const bits = [m.year, item.ext.toUpperCase(), fmtSize(item.size)].filter(Boolean);
        $('#audioMeta').textContent = bits.join(' · ');
      }
      if (m.has_cover) {
        const cover = $('#audioCover');
        if (cover) {
          cover.classList.add('has-img');
          cover.style.backgroundImage = `url("/api/audio_cover?${qs({ path: item.path })}")`;
          cover.innerHTML = '';
        }
      }
    } catch (_) { /* 没有标签信息就用文件名 */ }
  }

  async function renderPreview(item) {
    const body = $('#previewBody');
    stopMedia(body);   // 换一个文件预览时，先停掉上一个在放的音视频
    const newTab = $('#previewOpenNew');
    newTab.hidden = true;
    body.classList.remove('doc-mode');
    body.innerHTML = '<div class="preview-fallback"><p>加载中…</p></div>';
    const raw = `/api/raw?${qs({ path: item.path })}`;

    if (item.kind === 'image') {
      body.innerHTML = `<img src="${raw}" alt="${esc(item.name)}">`;
    } else if (item.kind === 'video') {
      body.innerHTML = `<video src="${raw}" controls autoplay playsinline></video>`;
    } else if (item.kind === 'audio') {
      await renderAudio(item, body);
    } else if (item.kind === 'pdf') {
      body.innerHTML = `<iframe src="${raw}" title="pdf"></iframe>`;
      newTab.href = raw;
      newTab.hidden = false;
    } else if (item.kind === 'html') {
      const url = '/files/' + encodePath(item.path);
      body.innerHTML = `<iframe src="${url}" title="${esc(item.name)}" sandbox="allow-scripts allow-popups allow-forms allow-modals"></iframe>`;
      newTab.href = url;
      newTab.hidden = false;
    } else if (item.kind === 'markdown') {
      try {
        const r = await api(`/api/text?${qs({ path: item.path })}`);
        previewSource = r.content;
        body.classList.add('doc-mode');
        body.innerHTML = '<div class="doc-scroll"><article class="md-body"></article></div>';
        body.querySelector('.md-body').innerHTML = mdToHtml(r.content, item.path);
      } catch (e) {
        body.innerHTML = fallbackHTML(item, e.message);
      }
    } else if (item.kind === 'table') {
      try {
        const r = await api(`/api/text?${qs({ path: item.path })}`);
        previewSource = r.content;
        const delim = item.ext === 'tsv' ? '\t' : sniffDelim(r.content);
        body.classList.add('doc-mode');
        body.innerHTML = tableHTML(parseDelimited(r.content, delim));
      } catch (e) {
        body.innerHTML = fallbackHTML(item, e.message);
      }
    } else if (item.kind === 'text') {
      try {
        const r = await api(`/api/text?${qs({ path: item.path })}`);
        previewSource = r.content;
        body.innerHTML = '<pre></pre>';
        body.querySelector('pre').textContent = r.content;
      } catch (e) {
        body.innerHTML = fallbackHTML(item, e.message);
      }
    } else if (item.kind === 'archive') {
      await renderArchive(item, body);
    } else if (OFFICE_KINDS.includes(item.kind)) {
      await renderOffice(item, body);
    } else {
      body.innerHTML = fallbackHTML(item, '该格式暂不支持在线预览，请下载后查看');
    }
  }

  /* ---------------- 压缩包预览 ---------------- */
  async function renderArchive(item, body) {
    if (item.ext === 'rar' || item.ext === '7z') {
      body.innerHTML = fallbackHTML(item, 'RAR / 7z 暂不支持在线查看，请下载后用本地工具解压');
      return;
    }
    body.classList.add('doc-mode');
    body.innerHTML = '<div class="ar-wrap"><div class="ar-loading">读取压缩包…</div></div>';
    let r;
    try {
      r = await api(`/api/archive?${qs({ path: item.path })}`);
    } catch (e) {
      body.classList.remove('doc-mode');
      body.innerHTML = fallbackHTML(item, e.message);
      return;
    }
    const entries = [...r.entries].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const files = entries.filter((en) => !en.dir);
    const total = files.reduce((s, en) => s + en.size, 0);
    const rows = entries.map((en) => {
      const bare = en.name.replace(/\/+$/, '');
      // zip 目录带尾斜杠，深度按路径段数算，封顶 5 层
      const depth = Math.min(bare.split('/').length - 1, 5);
      const nm = bare.split('/').pop() || en.name;
      return `<div class="ar-row" style="--d:${depth}">
        <span class="ar-ico">${en.dir ? icon('folder') : iconForPath(en.name)}</span>
        <span class="ar-nm" title="${esc(en.name)}">${esc(nm)}${en.dir ? '/' : ''}</span>
        <span class="ar-sz">${en.dir ? '—' : fmtSize(en.size)}</span>
        <span class="ar-tm">${fmtTime(en.mtime)}</span>
      </div>`;
    }).join('');

    body.innerHTML = `<div class="ar-wrap">
      <div class="ar-bar">
        <span class="ar-sum">共 ${r.total} 项 · 文件 ${files.length} 个 · 解压后约 ${fmtSize(total)}${r.truncated ? `（仅显示前 ${entries.length} 项）` : ''}</span>
        ${r.encrypted
          ? '<span class="ar-note">加密压缩包，暂不支持在线解压，可下载后输入密码解压</span>'
          : r.type === 'single' ? '' : '<button class="btn-primary" id="arExtract">解压到当前文件夹</button>'}
      </div>
      <div class="ar-list">${rows || '<div class="ar-empty">压缩包里没有内容</div>'}</div>
    </div>`;

    const btn = $('#arExtract');
    if (btn) btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = '解压中…';
      try {
        const r2 = await api('/api/archive/extract', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: item.path }),
        });
        toast(`已解压 ${r2.count} 项到「${r2.dest}/」`);
        closeModal('#previewModal');
        const parts = item.path.split('/');
        parts.pop();
        await loadDir(parts.join('/'));
      } catch (e) {
        toast(e.message, 'err');
        btn.disabled = false;
        btn.textContent = '解压到当前文件夹';
      }
    });
  }

  document.addEventListener('click', (e) => {
    const tab = e.target.closest('.sheet-tab');
    if (tab) paintSheet(+tab.dataset.sheet);
  });

  async function openPreview(item) {
    previewItem = item;
    previewSource = '';
    editing = false;
    $('#previewName').textContent = item.name;
    $('#previewMeta').textContent = `${fmtSize(item.size)} · ${fmtTime(item.mtime)}`;
    const dl = $('#previewDownload');
    dl.href = `/api/download?${qs({ path: item.path })}`;
    dl.setAttribute('download', item.name);
    const editBtn = $('#previewEdit');
    editBtn.hidden = !EDITABLE.includes(item.kind);
    editBtn.title = '编辑源码';
    openModal('#previewModal');
    await renderPreview(item);
  }

  function fallbackHTML(item, msg) {
    return `<div class="preview-fallback">
      <div class="pf-icon">${icon(item.kind)}</div>
      <p>${esc(msg)}</p>
      <a class="btn-primary" href="/api/download?${qs({ path: item.path })}" download>下载文件</a>
    </div>`;
  }

  $('#previewEdit').addEventListener('click', async () => {
    const body = $('#previewBody');
    if (!previewItem) return;

    if (editing) {
      const ta = body.querySelector('textarea');
      if (!ta) return;
      try {
        await api('/api/save_text', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: previewItem.path, content: ta.value }),
        });
        toast('已保存');
        editing = false;
        $('#previewEdit').title = '编辑源码';
        await renderPreview(previewItem);
        refresh();
      } catch (e) { toast(e.message, 'err'); }
      return;
    }

    if (!previewSource) {
      try {
        const r = await api(`/api/text?${qs({ path: previewItem.path })}`);
        previewSource = r.content;
      } catch (e) { toast(e.message, 'err'); return; }
    }
    const ta = document.createElement('textarea');
    ta.value = previewSource;
    ta.spellcheck = false;
    body.innerHTML = '';
    body.appendChild(ta);
    ta.focus();
    editing = true;
    $('#previewEdit').title = '保存';
  });

  /* ================= 分享链接 ================= */
  const shareState = { token: '', url: '', paths: [] };

  function shareLinkNow() {
    if (!shareState.url) return '';
    if (!$('#shareDirect').checked) return shareState.url;
    return shareState.url + (shareState.url.includes('?') ? '&' : '?') + 'dl=1';
  }

  function syncShareUI() {
    const link = shareLinkNow();
    $('#shareLink').value = link;
    if (link) $('#shareQrImg').src = `/api/qr?${qs({ text: link })}`;
  }

  function applyShare(s) {
    shareState.token = s.token;
    shareState.url = s.url;
    $('#shareRevoke').classList.remove('hidden');
    $('#shareQr').classList.remove('hidden');
    syncShareUI();
    refreshShareBadge();        // 侧栏「我的分享」角标跟着变
  }

  // 同一个文件反复点「分享」不该堆出一串没用的链接，先找找有没有现成的
  function daysOptionOf(expires) {
    if (!expires) return 0;
    const left = Math.max(0, expires - Date.now() / 1000);
    if (left <= 1.6 * 86400) return 1;
    if (left <= 15 * 86400) return 7;
    if (left <= 90 * 86400) return 30;
    return 0;
  }

  async function findShare(paths) {
    try {
      const d = await api('/api/shares');
      const key = (list) => list.slice().sort().join('\n');
      const want = key(paths);
      return (d.items || []).find((s) => key(s.paths || []) === want) || null;
    } catch (_) { return null; }
  }

  // 统一入口：任何异常都冒个提示，别让按钮看起来"点了没反应"
  function startShare(paths, label) {
    return openShare(paths, label).catch((e) => toast('分享没打开：' + (e && e.message ? e.message : e), 'err'));
  }

  async function openShare(paths, label) {
    const seq = (shareState.seq = (shareState.seq || 0) + 1);
    const stale = () => seq !== shareState.seq;

    shareState.token = '';
    shareState.url = '';
    shareState.paths = (paths || []).filter(Boolean);
    if (!shareState.paths.length) { toast('先选一个文件', 'err'); return; }

    const many = shareState.paths.length > 1;
    $('#shareTitle').textContent = label ? `分享「${label}」` : '分享链接';
    $('#shareSub').textContent = many
      ? `${shareState.paths.length} 项内容会打包成一个 zip，同一 WiFi 下打开链接即可下载`
      : '同一 WiFi 下，任何人打开这个链接都能访问';
    $('#shareLink').value = '正在生成…';
    $('#shareQr').classList.add('hidden');
    $('#shareRevoke').classList.add('hidden');
    openModal('#shareModal');

    const old = await findShare(shareState.paths);
    if (stale()) return;
    if (old && !$('#shareModal').classList.contains('hidden')) {
      $('#shareExpire').value = String(daysOptionOf(old.expires));
      applyShare(old);
      return;
    }

    try {
      const r = await api('/api/share', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: shareState.paths, days: +$('#shareExpire').value, label }),
      });
      if (stale()) return;
      applyShare(r.share);
    } catch (e) {
      if (stale()) return;
      $('#shareLink').value = '';
      $('#shareSub').textContent = e.message;
      toast(e.message, 'err');
    }
  }

  $('#shareLink').addEventListener('click', (e) => e.target.select());

  $('#previewShare').addEventListener('click', () => {
    if (previewItem) startShare([previewItem.path], previewItem.name);
    else toast('先打开一个文件再分享', 'err');
  });

  $('#selShare').addEventListener('click', () => {
    const paths = Array.from(state.sel);
    if (!paths.length) { toast('先选一个文件', 'err'); return; }
    const name = paths.length === 1 ? paths[0].split('/').pop() : '';
    openShare(paths, name).catch((e) => toast('分享没打开：' + (e && e.message ? e.message : e), 'err'));
  });

  $('#shareCopy').addEventListener('click', async () => {
    const link = shareLinkNow();
    if (!link) { toast('链接还没生成好', 'err'); return; }
    const ok = await copyText(link);
    if (ok) {
      toast('链接已复制，发给同一 WiFi 下的人就能打开');
    } else {
      const input = $('#shareLink');
      input.focus();
      input.select();
      toast('浏览器拦住了自动复制，链接已选中，按 Ctrl+C 复制', 'err');
    }
  });

  $('#shareDirect').addEventListener('change', syncShareUI);

  $('#shareExpire').addEventListener('change', async () => {
    if (!shareState.token) return;
    const days = +$('#shareExpire').value;
    try {
      const r = await api(`/api/share/${encodeURIComponent(shareState.token)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      });
      applyShare(r.share);
      toast(days ? `有效期已改为 ${days} 天` : '已设为永久有效');
    } catch (e) { toast(e.message, 'err'); }
  });

  $('#shareOpenNew').addEventListener('click', () => {
    const link = shareLinkNow();
    if (link) window.open(link, '_blank', 'noopener');
  });

  $('#shareRevoke').addEventListener('click', async () => {
    if (!shareState.token) return;
    const ok = await askConfirm({
      title: '取消这个分享？',
      text: '链接会立刻失效，已经收到链接的人也打不开了。',
      okText: '取消分享',
    });
    if (!ok) return;
    try {
      await api(`/api/share/${encodeURIComponent(shareState.token)}`, { method: 'DELETE' });
      shareState.token = '';
      closeModal('#shareModal');
      refreshShareBadge();
      toast('分享已取消');
    } catch (e) { toast(e.message, 'err'); }
  });

  $('#shareQrImg').addEventListener('error', () => $('#shareQr').classList.add('hidden'));

  /* ---------------- 我的分享（管理页） ---------------- */
  const sharePage = { items: [], loaded: false };

  const PATH_KINDS = {
    jpg: 'image', jpeg: 'image', png: 'image', gif: 'image', webp: 'image', bmp: 'image', svg: 'image', heic: 'image',
    mp4: 'video', mov: 'video', mkv: 'video', webm: 'video', avi: 'video', m4v: 'video',
    mp3: 'audio', wav: 'audio', flac: 'audio', m4a: 'audio', aac: 'audio', ogg: 'audio',
    pdf: 'pdf', txt: 'text', md: 'markdown', markdown: 'markdown', csv: 'table',
    html: 'html', htm: 'html', json: 'text', log: 'text',
    doc: 'word', docx: 'word', xls: 'excel', xlsx: 'excel', ppt: 'ppt', pptx: 'ppt',
    zip: 'archive', rar: 'archive', '7z': 'archive', tar: 'archive', gz: 'archive',
  };

  function iconForPath(p) {
    const name = String(p || '').split('/').pop();
    const dot = name.lastIndexOf('.');
    if (dot <= 0) return icon('folder');        // 没有扩展名，按文件夹画
    return icon(PATH_KINDS[name.slice(dot + 1).toLowerCase()] || 'file');
  }

  function setSharesVisible(on) {
    document.body.classList.toggle('shares-view', on);
    $('#content').classList.toggle('shares-mode', on);
    $('#sharesView').classList.toggle('hidden', !on);
    $('#subbar').classList.toggle('hidden', on);
    if (on) {
      $('#selActions').classList.add('hidden');
      $('#statusRight').textContent = '';
      $('#statusCount').textContent = '我的分享';
    }
  }

  function leaveSharesUI() {
    if (!document.body.classList.contains('shares-view')) return;
    setSharesVisible(false);
  }

  async function enterShares() {
    await flushNote();
    leaveNotesUI();
    leaveSettingsUI();
    setSharesVisible(true);
    state.view = 'shares';
    state.query = '';
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    $('#sidebar').classList.remove('open');
    renderCrumbs();
    syncNav();
    history.replaceState(null, '', location.pathname + '?view=shares');
    loadShares(true);
  }

  async function refreshShareBadge() {
    try {
      const d = await api('/api/shares');
      sharePage.items = d.items || [];
      sharePage.loaded = true;
      const n = sharePage.items.length;
      const el = $('#sideShareBadge');
      if (el) { el.textContent = n ? String(n) : ''; el.classList.toggle('on', n > 0); }
      return sharePage.items;
    } catch (_) { return []; }
  }

  function shareExpireText(s) {
    if (!s.expires) return '永久有效';
    const left = s.expires_in;
    if (left <= 0) return '已过期';
    const days = Math.ceil(left / 86400);
    if (days <= 1) {
      const hours = Math.max(1, Math.ceil(left / 3600));
      return hours <= 24 ? `${hours} 小时后过期` : '1 天后过期';
    }
    return `${days} 天后过期`;
  }

  function shareItemHTML(s) {
    const expired = s.expires > 0 && s.expires_in <= 0;
    const days = daysOptionOf(s.expires);
    const opts = [[1, '1 天'], [7, '7 天'], [30, '30 天'], [0, '永久']]
      .map(([v, t]) => `<option value="${v}"${v === days ? ' selected' : ''}>${t}</option>`).join('');
    const pathOne = (s.paths && s.paths[0]) || '';
    const sub = [
      `创建于 ${fmtTime(s.created)}`,
      expired ? '已过期' : shareExpireText(s),
      s.hits ? `打开 ${s.hits} 次` : '还没人打开',
    ].join(' · ');
    return `<article class="share-card${expired ? ' off' : ''}" data-token="${esc(s.token)}">
      <div class="sc-head">
        <span class="sc-icon">${iconForPath(pathOne)}</span>
        <div class="sc-title">
          <strong title="${esc(s.label)}">${esc(s.label)}</strong>
          <small>${esc(sub)}</small>
        </div>
        <span class="sc-state${expired ? ' off' : ''}">${expired ? '已过期' : '生效中'}</span>
      </div>
      <div class="sc-link">
        <input type="text" readonly spellcheck="false" value="${esc(s.url)}" data-url>
        <button class="mini-btn" data-act="copy">复制</button>
      </div>
      <div class="sc-foot">
        <label class="sc-expire">
          有效期
          <select data-act="days">${opts}</select>
        </label>
        <span class="sc-spacer"></span>
        <button class="mini-btn ghost" data-act="open">打开</button>
        <button class="mini-btn danger" data-act="revoke">取消分享</button>
      </div>
    </article>`;
  }

  function renderShares() {
    const list = $('#sharesList');
    const items = sharePage.items;
    const live = items.filter((s) => !(s.expires > 0 && s.expires_in <= 0)).length;
    $('#sharesCount').textContent = items.length ? `${items.length} 条` : '';
    $('#statusCount').textContent = items.length
      ? `${items.length} 条分享${items.length > live ? ` · ${items.length - live} 条已过期` : ''}`
      : '我的分享';
    $('#sharesEmpty').classList.toggle('hidden', items.length > 0);
    list.classList.toggle('hidden', items.length === 0);
    if (!items.length) { list.innerHTML = ''; return; }
    // 已过期的排后面，其余按创建时间倒序
    const sorted = items.slice().sort((a, b) => {
      const ea = a.expires > 0 && a.expires_in <= 0 ? 1 : 0;
      const eb = b.expires > 0 && b.expires_in <= 0 ? 1 : 0;
      if (ea !== eb) return ea - eb;
      return (b.created || 0) - (a.created || 0);
    });
    list.innerHTML = sorted.map(shareItemHTML).join('');
  }

  async function loadShares(force) {
    if (sharePage.loaded && !force) { renderShares(); return; }
    $('#sharesEmpty').classList.add('hidden');
    if (!sharePage.items.length) {
      $('#sharesList').innerHTML = '<div class="sc-loading">正在读取…</div>';
      $('#sharesList').classList.remove('hidden');
    }
    const items = await refreshShareBadge();
    sharePage.items = items;
    renderShares();
  }

  $('#sharesRefresh').addEventListener('click', () => loadShares(true));

  $('#sharesList').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const card = btn.closest('.share-card');
    const token = card && card.dataset.token;
    const item = sharePage.items.find((x) => x.token === token);
    if (!item) return;
    const act = btn.dataset.act;

    if (act === 'copy') {
      const ok = await copyText(item.url);
      if (ok) toast('链接已复制');
      else {
        const input = card.querySelector('[data-url]');
        input.focus(); input.select();
        toast('浏览器拦住了自动复制，链接已选中，按 Ctrl+C 复制', 'err');
      }
      return;
    }

    if (act === 'open') {
      window.open(item.url, '_blank', 'noopener');
      return;
    }

    if (act === 'revoke') {
      const ok = await askConfirm({
        title: `取消「${item.label}」的分享？`,
        text: '链接会立刻失效，已经收到链接的人也打不开了。文件本身不会删除。',
        okText: '取消分享',
      });
      if (!ok) return;
      try {
        await api(`/api/share/${encodeURIComponent(token)}`, { method: 'DELETE' });
        sharePage.items = sharePage.items.filter((x) => x.token !== token);
        renderShares();
        refreshShareBadge();
        toast('分享已取消');
      } catch (err) { toast(err.message, 'err'); }
    }
  });

  $('#sharesList').addEventListener('change', async (e) => {
    const sel = e.target.closest('[data-act="days"]');
    if (!sel) return;
    const card = sel.closest('.share-card');
    const token = card && card.dataset.token;
    if (!token) return;
    const days = +sel.value;
    try {
      const r = await api(`/api/share/${encodeURIComponent(token)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      });
      const i = sharePage.items.findIndex((x) => x.token === token);
      if (i >= 0) sharePage.items[i] = r.share;
      renderShares();
      toast(days ? `有效期已改为 ${days} 天` : '已设为永久有效');
    } catch (err) { toast(err.message, 'err'); }
  });

  // 长按/点击已生成的链接直接全选，方便手动复制
  $('#sharesList').addEventListener('focusin', (e) => {
    if (e.target.matches('[data-url]')) e.target.select();
  });

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === 's' || e.key === 'S') && state.view === 'notes') {
      e.preventDefault();
      forceSaveNote();
      return;
    }
    if (e.key === 'Escape') {
      $$('.modal').forEach((m) => hideModal(m));
      $('#dropMask').classList.remove('show');
      $('#sidebar').classList.remove('open');
    }
    // 按 / 聚焦搜索（在没有输入框聚焦时）
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey
      && !/^(input|textarea|select)$/i.test(document.activeElement.tagName)
      && state.view !== 'notes' && state.view !== 'settings' && state.view !== 'shares') {
      e.preventDefault();
      $('#searchInput').focus();
      $('#searchInput').select();
      return;
    }
    if ((e.key === 'Delete' || e.key === 'Backspace') && state.sel.size && !/input|textarea/i.test(document.activeElement.tagName)) {
      e.preventDefault();
      const paths = Array.from(state.sel);
      doDelete(paths, paths.length === 1 ? paths[0].split('/').pop() : `${paths.length} 个项目`);
    }
  });

  /* ================= 网络笔记 ================= */
  const NOTE_PANES = (window.matchMedia && window.matchMedia('(max-width: 980px)').matches)
    ? ['edit', 'preview'] : ['split', 'preview', 'edit'];

  const PIN_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4h6l-1 5 3 3v1H7v-1l3-3-1-5Z"/><path d="M12 13v7"/></svg>';

  const nt = {
    items: [],
    id: '',
    title: '',
    content: '',
    pinned: false,
    dirty: false,
    saving: false,
    ver: 0,
    timer: 0,
    prevTimer: 0,
    savedAt: 0,
    pane: NOTE_PANES.includes(localStorage.getItem('landisk.notePane'))
      ? localStorage.getItem('landisk.notePane') : NOTE_PANES[0],
  };

  const noteEl = {
    view: () => $('#notesView'),
    input: () => $('#noteInput'),
    preview: () => $('#notePreview'),
    title: () => $('#noteTitle'),
    status: () => $('#noteStatus'),
  };

  function hhmm(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function setNotesVisible(on) {
    document.body.classList.toggle('notes-view', on);
    $('#content').classList.toggle('notes-mode', on);
    $('#notesView').classList.toggle('hidden', !on);
    $('#subbar').classList.toggle('hidden', on);
    $('#searchInput').placeholder = on ? '搜索笔记…' : '搜索文件…';
    $('#btnUploadLabel').textContent = on ? '新建笔记' : '上传文件';
    $('#btnUploadMain').querySelector('.ico-upload').classList.toggle('hidden', on);
    $('#btnUploadMain').querySelector('.ico-note').classList.toggle('hidden', !on);
    if (on) { $('#selActions').classList.add('hidden'); applyPane(); }
    else { $('#statusRight').textContent = ''; }
  }

  function leaveNotesUI() {
    if (!document.body.classList.contains('notes-view')) return;
    flushNote();
    setNotesVisible(false);
  }

  function applyPane() {
    noteEl.view().dataset.pane = nt.pane;
    localStorage.setItem('landisk.notePane', nt.pane);
    const btn = $('#notePane');
    if (btn) btn.title = nt.pane === 'split' ? '当前：编辑 + 预览' : nt.pane === 'preview' ? '当前：只看预览' : '当前：只看编辑';
  }

  async function enterNotes() {
    if (state.view === 'notes') { await loadNotes(); return; }
    await flushNote();
    leaveSettingsUI();
    leaveSharesUI();
    state.view = 'notes';
    state.query = '';
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    $('#sidebar').classList.remove('open');
    setNotesVisible(true);
    renderCrumbs();
    syncNav();
    history.replaceState(null, '', location.pathname + '?view=notes');
    await loadNotes();
  }

  async function loadNotes() {
    let data;
    try {
      data = await api(`/api/notes?${qs({ q: state.query })}`);
    } catch (e) {
      toast(e.message, 'err');
      return;
    }
    nt.items = data.items || [];
    const stillThere = nt.id && nt.items.some((i) => i.id === nt.id);
    if (!stillThere && !nt.dirty) {
      if (nt.items.length) { nt.id = ''; await openNote(nt.items[0].id); }
      else if (!state.query) showNoteBlank();
    } else if (!nt.id && nt.items.length) {
      await openNote(nt.items[0].id);
    }
    renderNoteList();
    updateNoteBar();
  }

  function renderNoteList() {
    const box = $('#noteList');
    if (!box) return;
    $('#noteCount').textContent = nt.items.length;
    if (!nt.items.length) {
      box.innerHTML = `<div class="note-list-empty">${state.query ? '没有匹配的笔记' : '还没有笔记，点右上角「新建」'}</div>`;
      return;
    }
    box.innerHTML = nt.items.map((it) => `
      <div class="note-item ${it.id === nt.id ? 'active' : ''}" data-id="${esc(it.id)}">
        <div class="note-item-top">
          <span class="note-item-title">${esc(it.title || '无标题笔记')}</span>
          ${it.pinned ? `<span class="note-item-pin">${PIN_SVG}</span>` : ''}
        </div>
        <div class="note-item-ex">${esc(it.excerpt || '空白笔记')}</div>
        <div class="note-item-time">${fmtTime(it.updated)} · ${it.chars} 字</div>
      </div>`).join('');
  }

  function updateNoteBar() {
    const chars = nt.items.reduce((s, i) => s + (i.chars || 0), 0);
    $('#statusCount').textContent = nt.items.length
      ? `${nt.items.length} 篇笔记 · 共 ${chars} 字`
      : '还没有笔记';
    $('#statusRight').textContent = nt.items.length ? '自动保存已开启 · Ctrl+S 手动保存' : '';
    $('#subbarLeft').textContent = '';
  }

  function updateNoteStatus() {
    const el = noteEl.status();
    if (!el) return;
    if (!nt.id) { el.textContent = ''; el.className = 'note-status'; return; }
    if (nt.saving) { el.textContent = '保存中…'; el.className = 'note-status'; return; }
    if (nt.dirty) { el.textContent = '未保存'; el.className = 'note-status dirty'; return; }
    const chars = (nt.content || '').length;
    el.textContent = `${chars} 字 · 已保存 ${hhmm(nt.savedAt)}`;
    el.className = 'note-status ok';
  }

  function paintPin() {
    const b = $('#notePin');
    if (b) b.classList.toggle('on', nt.pinned);
  }

  function paintNotePreview(now) {
    const draw = () => {
      const box = noteEl.preview();
      if (!box) return;
      const html = mdToHtml(nt.content || '', '');
      box.innerHTML = html || '<p class="note-placeholder">左边写点什么，这里就是它的样子。</p>';
    };
    if (now) { draw(); return; }
    clearTimeout(nt.prevTimer);
    nt.prevTimer = setTimeout(draw, 130);
  }

  async function openNote(id) {
    if (!id) return;
    await flushNote();
    let n;
    try {
      n = await api(`/api/notes/${encodeURIComponent(id)}`);
    } catch (e) {
      toast(e.message, 'err');
      return;
    }
    nt.id = n.id;
    nt.title = n.title_raw || '';
    nt.content = n.content || '';
    nt.pinned = !!n.pinned;
    nt.dirty = false;
    nt.saving = false;
    nt.savedAt = n.updated;
    noteEl.title().value = nt.title;
    noteEl.title().placeholder = n.title || '无标题笔记';
    noteEl.input().value = nt.content;
    noteEl.input().scrollTop = 0;
    paintNotePreview(true);
    $('#noteBlank').classList.add('hidden');
    $('#noteMain').classList.remove('hidden');
    noteEl.view().classList.add('mobile-edit');
    paintPin();
    updateNoteStatus();
    renderNoteList();
    updateNoteBar();
  }

  function showNoteBlank() {
    nt.id = '';
    nt.title = '';
    nt.content = '';
    nt.dirty = false;
    noteEl.title().value = '';
    noteEl.title().placeholder = '无标题笔记';
    noteEl.input().value = '';
    $('#noteMain').classList.add('hidden');
    $('#noteBlank').classList.remove('hidden');
    noteEl.view().classList.remove('mobile-edit');
    renderNoteList();
  }

  function updateNoteMeta(note) {
    const i = nt.items.findIndex((x) => x.id === note.id);
    if (i >= 0) nt.items[i] = note;
    nt.items.sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.updated - a.updated);
    renderNoteList();
    updateNoteBar();
  }

  async function saveNote() {
    if (!nt.id || !nt.dirty || nt.saving) return false;
    const ver = nt.ver;
    nt.saving = true;
    updateNoteStatus();
    try {
      const r = await api(`/api/notes/${encodeURIComponent(nt.id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: noteEl.title().value, content: nt.content }),
      });
      nt.savedAt = r.note.updated;
      if (nt.ver === ver) nt.dirty = false;
      nt.title = r.note.title_raw || '';
      if (!noteEl.title().value.trim()) noteEl.title().placeholder = r.note.title;
      updateNoteMeta(r.note);
      return true;
    } catch (e) {
      toast(e.message, 'err');
      return false;
    } finally {
      nt.saving = false;
      updateNoteStatus();
    }
  }

  async function flushNote() {
    if (nt.timer) { clearTimeout(nt.timer); nt.timer = 0; }
    if (nt.id && nt.dirty) await saveNote();
  }

  async function forceSaveNote() {
    if (!nt.id) return;
    nt.dirty = true;
    const ok = await saveNote();
    if (ok) toast('已保存');
  }

  function scheduleNoteSave() {
    nt.ver++;
    nt.dirty = true;
    updateNoteStatus();
    clearTimeout(nt.timer);
    nt.timer = setTimeout(() => { nt.timer = 0; saveNote(); }, 900);
  }

  function onNoteInput() {
    nt.content = noteEl.input().value;
    scheduleNoteSave();
    paintNotePreview();
  }

  async function newNote() {
    await flushNote();
    try {
      const r = await api('/api/notes', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '', content: '' }),
      });
      nt.id = '';
      if (state.query) {
        state.query = '';
        $('#searchInput').value = '';
        $('#searchClear').classList.add('hidden');
        renderCrumbs();
      }
      nt.items.unshift(r.note);
      await openNote(r.note.id);
      noteEl.input().focus();
    } catch (e) { toast(e.message, 'err'); }
  }

  /* ---- Markdown 工具栏 ---- */
  function wrapSel(prefix, suffix, placeholder) {
    const ta = noteEl.input();
    ta.focus();
    const s = ta.selectionStart, e = ta.selectionEnd;
    const sel = ta.value.slice(s, e) || placeholder;
    ta.setRangeText(prefix + sel + suffix, s, e, 'select');
    ta.selectionStart = s + prefix.length;
    ta.selectionEnd = s + prefix.length + sel.length;
    onNoteInput();
  }

  function prefixLines(p) {
    const ta = noteEl.input();
    ta.focus();
    const val = ta.value;
    const s = ta.selectionStart;
    const from = val.lastIndexOf('\n', s - 1) + 1;
    let to = val.indexOf('\n', ta.selectionEnd);
    if (to === -1) to = val.length;
    const lines = val.slice(from, to).split('\n');
    const probe = typeof p === 'string' ? p : p(0);
    const filled = lines.filter((l) => l.trim());
    const all = filled.length > 0 && filled.every((l) => l.trimStart().startsWith(probe));
    const split = (l) => {
      const m = /^(\s*)((?:#{1,6}\s+|[-*+>]\s+|\d+[.)]\s+|\[[ xX]\]\s+)+)/.exec(l);
      return m ? [m[1], l.slice(m[0].length)] : [/^\s*/.exec(l)[0], l.trimStart()];
    };
    const out = lines.map((l, i) => {
      if (!l.trim()) return l;
      const [indent, body] = split(l);
      return all ? indent + body : indent + (typeof p === 'string' ? p : p(i)) + body;
    }).join('\n');
    ta.setRangeText(out, from, to, 'select');
    onNoteInput();
  }

  function insertNoteText(text) {
    const ta = noteEl.input();
    ta.focus();
    const s = ta.selectionStart;
    const before = ta.value.slice(0, s);
    const pad = !before ? '' : before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n';
    ta.setRangeText(pad + text + '\n', s, ta.selectionEnd, 'end');
    onNoteInput();
  }

  function insertLink() {
    const ta = noteEl.input();
    ta.focus();
    const s = ta.selectionStart, e = ta.selectionEnd;
    const label = ta.value.slice(s, e) || '链接文字';
    const out = `[${label}](https://)`;
    ta.setRangeText(out, s, e, 'select');
    ta.selectionStart = s + label.length + 3;
    ta.selectionEnd = s + out.length - 1;
    onNoteInput();
  }

  function mdAction(act) {
    if (!nt.id) { toast('先新建一篇笔记'); return; }
    switch (act) {
      case 'bold': return wrapSel('**', '**', '粗体');
      case 'italic': return wrapSel('*', '*', '斜体');
      case 'strike': return wrapSel('~~', '~~', '删除线');
      case 'code': return wrapSel('`', '`', 'code');
      case 'h1': return prefixLines('# ');
      case 'h2': return prefixLines('## ');
      case 'h3': return prefixLines('### ');
      case 'ul': return prefixLines('- ');
      case 'ol': return prefixLines((i) => `${i + 1}. `);
      case 'task': return prefixLines('- [ ] ');
      case 'quote': return prefixLines('> ');
      case 'link': return insertLink();
      case 'table': return insertNoteText('| 列 1 | 列 2 |\n| --- | --- |\n| 内容 | 内容 |');
      case 'hr': return insertNoteText('---');
      case 'image': return $('#noteImagePicker').click();
      default: return undefined;
    }
  }

  async function uploadNoteImage(file) {
    if (!nt.id) { toast('先新建一篇笔记'); return; }
    if (file.size > 20 * 1024 * 1024) { toast('图片超过 20MB', 'err'); return; }
    const fd = new FormData();
    fd.append('file', file, file.name || 'image.png');
    try {
      const r = await api('/api/notes/media', { method: 'POST', body: fd });
      const alt = String(r.name || '图片').replace(/[[\]]/g, '');
      insertNoteText(`![${alt}](${r.url})`);
      toast('图片已插入');
    } catch (e) { toast(e.message, 'err'); }
  }

  function exportNote() {
    if (!nt.id) return;
    const raw = (noteEl.title().value || '').trim() || '无标题笔记';
    const name = raw.replace(/[\\/:*?"<>|\r\n\t]/g, '_') + '.md';
    const blob = new Blob([nt.content || ''], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  /* ---- 事件 ---- */
  $('#noteNew').addEventListener('click', newNote);
  $('#noteBlankNew').addEventListener('click', newNote);
  $('#noteSave').addEventListener('click', forceSaveNote);
  $('#noteExport').addEventListener('click', exportNote);

  $('#notePane').addEventListener('click', () => {
    const i = NOTE_PANES.indexOf(nt.pane);
    nt.pane = NOTE_PANES[(i + 1) % NOTE_PANES.length];
    applyPane();
  });

  $('#noteBack').addEventListener('click', async () => {
    await flushNote();
    noteEl.view().classList.remove('mobile-edit');
  });

  $('#noteList').addEventListener('click', (e) => {
    const el = e.target.closest('.note-item');
    if (el) openNote(el.dataset.id);
  });

  $('#noteTitle').addEventListener('input', () => {
    nt.title = noteEl.title().value;
    scheduleNoteSave();
  });

  $('#noteInput').addEventListener('input', onNoteInput);

  $('#noteInput').addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.target;
      ta.setRangeText('  ', ta.selectionStart, ta.selectionEnd, 'end');
      onNoteInput();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
      const k = e.key.toLowerCase();
      if (k === 'b') { e.preventDefault(); mdAction('bold'); }
      else if (k === 'i') { e.preventDefault(); mdAction('italic'); }
      else if (k === 'k') { e.preventDefault(); mdAction('link'); }
    }
  });

  $('#noteInput').addEventListener('paste', (e) => {
    const items = Array.from((e.clipboardData && e.clipboardData.items) || []);
    const imgs = items.filter((it) => it.kind === 'file' && /^image\//.test(it.type));
    if (!imgs.length) return;
    e.preventDefault();
    imgs.forEach((it) => { const f = it.getAsFile(); if (f) uploadNoteImage(f); });
  });

  $('#noteImagePicker').addEventListener('change', (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = '';
    files.forEach(uploadNoteImage);
  });

  $('#noteMdTools').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-md]');
    if (b) mdAction(b.dataset.md);
  });

  $('#notePin').addEventListener('click', async () => {
    if (!nt.id) return;
    try {
      const r = await api(`/api/notes/${encodeURIComponent(nt.id)}/pin`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !nt.pinned }),
      });
      nt.pinned = !!r.note.pinned;
      paintPin();
      updateNoteMeta(r.note);
      toast(nt.pinned ? '已置顶' : '已取消置顶');
    } catch (e) { toast(e.message, 'err'); }
  });

  $('#noteDelete').addEventListener('click', async () => {
    if (!nt.id) return;
    const label = (noteEl.title().value || '').trim() || '无标题笔记';
    const ok = await askConfirm({ title: '删除笔记？', text: `「${label}」删除后无法恢复。` });
    if (!ok) return;
    try {
      await api(`/api/notes/${encodeURIComponent(nt.id)}`, { method: 'DELETE' });
      clearTimeout(nt.timer);
      nt.timer = 0;
      nt.dirty = false;
      nt.items = nt.items.filter((i) => i.id !== nt.id);
      nt.id = '';
      toast('笔记已删除');
      if (nt.items.length) await openNote(nt.items[0].id);
      else { showNoteBlank(); updateNoteBar(); }
    } catch (e) { toast(e.message, 'err'); }
  });

  window.addEventListener('beforeunload', (e) => {
    if (nt.dirty) { e.preventDefault(); e.returnValue = ''; }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && nt.dirty) flushNote();
  });

  /* ---------------- 系统设置 ---------------- */
  const setting = {
    tab: 'about',
    about: null,
    level: '',
    q: '',
    items: [],
    offset: 0,
    loading: false,
  };

  const ACTION_TAG = {
    'system.boot': '启动', 'system.stop': '停止',
    'auth.login': '登录', 'auth.fail': '登录', 'auth.set': '安全设置',
    upload: '上传', download: '下载', zip: '打包', mkdir: '新建',
    extract: '解压', share: '分享', remark: '备注',
    rename: '重命名', move: '移动', delete: '删除', copy: '复制', edit: '编辑',
    'log.clear': '日志', 'log.export': '日志',
    error: '异常',
  };
  function logTag(action) {
    if (ACTION_TAG[action]) return ACTION_TAG[action];
    if (String(action).startsWith('http.')) return '请求';
    if (String(action).startsWith('note.')) return '笔记';
    return '事件';
  }

  function pad2(n) { return String(n).padStart(2, '0'); }
  function fullTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }
  function uptimeText(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (d) return `${d} 天 ${h} 小时`;
    if (h) return `${h} 小时 ${m} 分`;
    if (m) return `${m} 分 ${sec % 60} 秒`;
    return `${sec} 秒`;
  }
  function dayKey(ts) {
    const d = new Date(ts * 1000);
    return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  }
  function dayLabel(ts) {
    const d = new Date(ts * 1000);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const that = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const diff = Math.round((today - that) / 86400000);
    const base = `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
    if (diff === 0) return `今天 · ${base}`;
    if (diff === 1) return `昨天 · ${base}`;
    if (diff === 2) return `前天 · ${base}`;
    return `${d.getFullYear()} 年 ${base}`;
  }

  function setSettingsVisible(on) {
    document.body.classList.toggle('settings-view', on);
    $('#content').classList.toggle('settings-mode', on);
    $('#settingsView').classList.toggle('hidden', !on);
    $('#subbar').classList.toggle('hidden', on);
    if (on) {
      $('#selActions').classList.add('hidden');
      $('#statusRight').textContent = '';
      $('#statusCount').textContent = '系统设置';
    }
  }

  function leaveSettingsUI() {
    if (!document.body.classList.contains('settings-view')) return;
    setSettingsVisible(false);
  }

  function setSettingsTab(tab) {
    setting.tab = ['logs', 'security'].includes(tab) ? tab : 'about';
    $('#settingsView').dataset.tab = setting.tab;
    $$('#setTabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === setting.tab));
    $('#paneAbout').classList.toggle('hidden', setting.tab !== 'about');
    $('#paneLogs').classList.toggle('hidden', setting.tab !== 'logs');
    $('#paneSecurity').classList.toggle('hidden', setting.tab !== 'security');
    $('#setBody').scrollTop = 0;
    if (setting.tab === 'logs') loadLogs(true);
    else if (setting.tab === 'security') loadSecurity();
    else loadAbout(true);
  }

  async function enterSettings(tab) {
    await flushNote();
    leaveNotesUI();
    leaveSettingsUI();
    leaveSharesUI();
    state.view = 'settings';
    state.query = '';
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    $('#sidebar').classList.remove('open');
    setSettingsVisible(true);
    renderCrumbs();
    syncNav();
    history.replaceState(null, '', location.pathname + '?view=settings');
    setSettingsTab(tab || setting.tab);
    refreshLogBadge();
  }

  async function loadAbout(force) {
    if (setting.about && !force) return;
    try {
      const d = await api('/api/about');
      setting.about = d;
      renderAbout(d);
    } catch (e) {
      toast(e.message, 'err');
    }
  }

  /* ---------------- 登录安全 ---------------- */

  async function loadSecurity() {
    try {
      const d = await api('/api/security');
      paintSecurity(d.enabled);
    } catch (e) {
      $('#secState').textContent = e.message;
    }
  }

  let secWasOn = false;             // 服务端当前的真实状态

  function paintSecurity(on) {
    secWasOn = on;
    $('#secToggle').checked = on;
    $('#secState').textContent = on
      ? '已开启 — 访问云盘需要输入口令，分享链接不受影响'
      : '未开启 — 同一局域网内任何人都能直接打开这个云盘';
    $('#secLabel').textContent = on ? '修改口令（可选）' : '访问口令';
    $('#secHint').textContent = on
      ? '输入新口令并保存即可修改；其他设备需要用新口令重新登录，当前浏览器保持登录。'
      : '开启或修改口令后，局域网内其他设备需要用新口令重新登录；当前浏览器保持登录，不用重输。';
    $('#secPwd').value = '';
    $('#secPwd').placeholder = on ? '留空则保持现有口令' : '设置访问口令';
  }

  async function saveSecurity(enabled) {
    const pwd = $('#secPwd').value.trim();
    const wasOn = secWasOn;
    if (enabled && !pwd && !secWasOn) {
      toast('请先设置口令', 'err');
      $('#secPwd').focus();
      return;
    }
    if (pwd && pwd.length < 4) {
      toast('口令至少 4 个字符', 'err');
      $('#secPwd').focus();
      return;
    }
    try {
      const r = await api('/api/security', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled, password: pwd }),
      });
      paintSecurity(r.enabled);
      setting.about = null;           // 「关于我们」里的口令状态要重新拉
      toast(r.enabled
        ? (!wasOn ? '密码登录已开启' : (pwd ? '口令已修改，其他设备需重新登录' : '已开启密码登录'))
        : '已关闭密码登录', 'ok');
      if (setting.tab === 'about') await loadAbout(true);
    } catch (e) {
      toast(e.message, 'err');
      paintSecurity(wasOn);           // 失败回滚开关显示
    }
  }

  function kvRow(key, value, cls) {
    return `<div class="kv"><dt>${esc(key)}</dt><dd class="${cls || ''}">${value}</dd></div>`;
  }

  function renderAbout(d) {
    $('#aboutVer').textContent = 'v' + d.version;
    $('#aboutTagline').textContent = d.tagline || '';
    const lan = (d.lan && d.lan[0]) || `${location.protocol}//${location.host}`;

    $('#aboutRun').innerHTML = [
      kvRow('服务地址', esc(lan.replace(/^http:\/\//, '')), 'accent'),
      kvRow('主机名', esc(d.host || '—')),
      kvRow('运行时长', `<span id="aboutUptime">${uptimeText(d.uptime)}</span>`),
      kvRow('启动时间', fullTime(d.started_at)),
      kvRow('访问口令', d.password ? '已开启，访问需要登录' : '未开启，局域网内可直接访问'),
    ].join('');

    $('#aboutEnv').innerHTML = [
      kvRow('Python', esc(d.python)),
      kvRow('FastAPI', esc(d.fastapi)),
      kvRow('操作系统', `${esc(d.os)} · ${esc(d.arch)}`),
      kvRow('存储目录', esc(d.storage_dir), 'mono'),
      kvRow('笔记目录', esc(d.notes_dir), 'mono'),
      kvRow('日志文件', esc(d.log_file), 'mono'),
    ].join('');

    const c = d.content || {};
    const n = d.notes || {};
    const g = d.logs || {};
    $('#aboutStats').innerHTML = [
      ['文件', c.files || 0, ''],
      ['文件夹', c.folders || 0, ''],
      ['云盘占用', fmtSize(c.size || 0), ''],
      ['笔记', n.count || 0, `${(n.chars || 0).toLocaleString()} 字`],
      ['日志', g.count || 0, `文件 ${fmtSize(g.file_size || 0)}`],
    ].map(([label, value, sub]) => `
      <div class="stat"><b>${esc(String(value))}</b><span>${esc(label)}${sub ? ' · ' + esc(sub) : ''}</span></div>
    `).join('');

    const disk = d.disk || { total: 1, free: 0 };
    const used = Math.max(0, disk.total - disk.free);
    const pct = Math.min(100, (used / (disk.total || 1)) * 100);
    $('#aboutDisk').innerHTML = `<span>磁盘 ${fmtSize(used)} / ${fmtSize(disk.total)}</span>
      <div class="meter"><i style="width:${pct.toFixed(1)}%"></i></div>
      <span>剩余 ${fmtSize(disk.free)}</span>`;

    $('#aboutBuild').textContent = `${d.os} · Python ${d.python} · 启动于 ${fullTime(d.started_at)}`;
  }

  function logItemHTML(row) {
    const t = new Date((row.ts || 0) * 1000);
    const detail = [row.detail, row.ip ? `来自 ${row.ip}` : ''].filter(Boolean).join(' · ');
    return `<div class="log-item lv-${esc(row.level || 'info')}">
      <span class="log-dot"></span>
      <span class="log-time">${pad2(t.getHours())}:${pad2(t.getMinutes())}:${pad2(t.getSeconds())}</span>
      <span class="log-tag">${esc(logTag(row.action))}</span>
      <span class="log-msg">${esc(row.message || row.action || '')}${detail ? `<span class="log-detail">${esc(detail)}</span>` : ''}</span>
    </div>`;
  }

  function paintLogCounts(counts) {
    if (!counts) return;
    $$('#logFilters button').forEach((b) => {
      const el = b.querySelector('b');
      const n = counts[b.dataset.level || 'all'] || 0;
      if (el) el.textContent = n > 999 ? '999+' : n;
    });
    const bad = counts.error || 0;
    const badge = $('#sideLogBadge');
    if (badge) {
      badge.textContent = bad > 99 ? '99+' : bad;
      badge.classList.toggle('on', bad > 0);
    }
  }

  async function refreshLogBadge() {
    try {
      const d = await api('/api/logs?limit=1');
      paintLogCounts(d.counts);
    } catch (_) { /* 忽略 */ }
  }

  async function loadLogs(reset) {
    if (setting.loading) return;
    setting.loading = true;
    if (reset) {
      setting.items = [];
      setting.offset = 0;
      $('#logList').innerHTML = '<div class="log-empty">正在读取日志…</div>';
    }
    try {
      const d = await api(`/api/logs?${qs({ level: setting.level, q: setting.q, limit: 100, offset: setting.offset })}`);
      setting.items = reset ? d.items : setting.items.concat(d.items);
      setting.offset = setting.items.length;
      renderLogs(d);
      paintLogCounts(d.counts);
    } catch (e) {
      toast(e.message, 'err');
      if (!setting.items.length) $('#logList').innerHTML = `<div class="log-empty">读取失败：${esc(e.message)}</div>`;
    } finally {
      setting.loading = false;
    }
  }

  function renderLogs(d) {
    const box = $('#logList');
    const items = setting.items;
    if (!items.length) {
      box.innerHTML = `<div class="log-empty">${setting.q || setting.level
        ? '没有符合条件的日志'
        : '还没有日志记录<br>上传、下载、删除、写笔记等操作都会自动记在这里'}</div>`;
    } else {
      let html = '';
      let last = '';
      items.forEach((row) => {
        const key = dayKey(row.ts);
        if (key !== last) {
          html += `<div class="log-day">${esc(dayLabel(row.ts))}</div>`;
          last = key;
        }
        html += logItemHTML(row);
      });
      box.innerHTML = html;
    }

    const filtered = setting.level || setting.q;
    $('#logHint').textContent = `${d.matched} 条${filtered ? '（已筛选）' : ''} · 日志文件 ${fmtSize(d.file_size || 0)}`;
    const more = $('#logMore');
    more.classList.toggle('hidden', !d.has_more);
    if (d.has_more) {
      $('#logMoreBtn').textContent = `加载更早的记录（还有 ${d.matched - items.length} 条）`;
    }
  }

  $('#btnSettings').addEventListener('click', () => enterSettings('about'));

  $('#setTabs').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-tab]');
    if (b) setSettingsTab(b.dataset.tab);
  });

  $('#secToggle').addEventListener('change', async () => {
    const on = $('#secToggle').checked;
    if (!on && secWasOn) {
      const ok = await askConfirm({
        title: '关闭密码登录',
        text: '关闭后，同一局域网内的任何设备都能直接打开这个云盘，不需要输口令。确定要关闭吗？',
        okText: '关闭',
      });
      if (!ok) { $('#secToggle').checked = true; return; }
    }
    saveSecurity(on);
  });

  $('#secSave').addEventListener('click', () => saveSecurity($('#secToggle').checked));

  $('#secLogout').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST' }); } catch (_) { /* 忽略 */ }
    location.reload();
  });

  $('#logFilters').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-level]');
    if (!b) return;
    setting.level = b.dataset.level || '';
    $$('#logFilters button').forEach((x) => x.classList.toggle('active', x === b));
    loadLogs(true);
  });

  let logTimer;
  $('#logSearch').addEventListener('input', (e) => {
    const v = e.target.value.trim();
    clearTimeout(logTimer);
    logTimer = setTimeout(() => {
      setting.q = v;
      loadLogs(true);
    }, 260);
  });

  $('#logRefresh').addEventListener('click', async () => {
    await loadLogs(true);
    if (setting.tab === 'about') await loadAbout(true);
    toast('已刷新');
  });

  $('#logMoreBtn').addEventListener('click', () => loadLogs(false));

  $('#logExport').addEventListener('click', () => {
    triggerDownload('/api/logs/export');
    toast('正在导出日志');
  });

  $('#logClear').addEventListener('click', async () => {
    const ok = await askConfirm({
      title: '清空系统日志？',
      text: '清空后无法恢复，只保留一条「日志已清空」的记录。',
      okText: '清空',
    });
    if (!ok) return;
    try {
      const r = await api('/api/logs', { method: 'DELETE' });
      toast(`已清空 ${r.removed} 条日志`);
      await loadLogs(true);
    } catch (e) {
      toast(e.message, 'err');
    }
  });

  /* ---------------- 侧栏 / 登录 ---------------- */
  $('#btnMenu').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  document.addEventListener('click', (e) => {
    const sb = $('#sidebar');
    if (window.innerWidth <= 820 && sb.classList.contains('open') && !sb.contains(e.target) && e.target.id !== 'btnMenu' && !e.target.closest('#btnMenu')) {
      sb.classList.remove('open');
    }
  });

  function showLogin() {
    $('#loginMask').classList.remove('hidden');
    setTimeout(() => $('#loginPwd').focus(), 50);
  }
  $('#loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pwd = $('#loginPwd').value;
    try {
      const res = await fetch('/api/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        $('#loginErr').textContent = d.detail || '口令错误';
        return;
      }
      $('#loginErr').textContent = '';
      $('#loginMask').classList.add('hidden');
      boot();
    } catch (_) { $('#loginErr').textContent = '网络错误'; }
  });

  /* ---------------- 启动 ---------------- */
  window.addEventListener('hashchange', () => {
    const p = decodeURI(location.hash.replace(/^#\/?/, ''));
    if (state.view === 'browse' && !state.query && p === state.path) return;
    state.query = '';
    $('#searchInput').value = '';
    $('#searchClear').classList.add('hidden');
    loadDir(p);
  });

  async function boot() {
    $('#brandHost').textContent = location.host;
    $('#sortSelect').value = state.sort;
    const params = new URLSearchParams(location.search);
    const v = params.get('view');
    const m = params.get('mode');
    if (m === 'grid' || m === 'list') state.mode = m;
    const hash = decodeURI(location.hash.replace(/^#\/?/, ''));
    try {
      const s = await api('/api/session');
      if (s.auth_required && !s.logged_in) { showLogin(); return; }
    } catch (_) { }
    if (v === 'settings') await enterSettings();
    else if (v === 'notes') await enterNotes();
    else if (v === 'shares') await enterShares();
    else if (v && TITLES[v]) await loadBrowse(v);
    else await loadDir(hash || '');
    updateStats();
    refreshLogBadge();
    refreshShareBadge();
  }

  setInterval(() => {
    if (state.view !== 'settings' || setting.tab !== 'about' || !setting.about) return;
    const el = $('#aboutUptime');
    if (el) el.textContent = uptimeText(Math.floor(Date.now() / 1000) - setting.about.started_at);
  }, 10000);

  initTheme();
  boot();
})();
