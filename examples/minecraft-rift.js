/* An opt-in local HTML playground. Actor positions come from a token-protected
 * loopback desktop bridge; actual DOM nodes are removed/created by user actions.
 * The Chrome toolbar and the source Minecraft game remain unchanged.
 */
(function (root) {
  'use strict';
  const KEY = 'windowrift-minecraft-block-arena-v1';
  const INITIAL = [
    {id: 'wood-a', kind: 'wood', x: 28, row: 0},
    {id: 'stone-b', kind: 'stone', x: 45, row: 0},
    {id: 'glass-c', kind: 'glass', x: 62, row: 0},
    {id: 'moss-d', kind: 'moss', x: 79, row: 0},
  ];
  const MAX_BLOCKS = 24;
  const MAX_IMAGE = 75000;
  const ACTIONS = new Set(['mine', 'place']);

  function validActor(a) {
    return !!a && Number.isInteger(a.id) &&
      [a.x, a.y, a.width, a.height].every(Number.isFinite) &&
      a.width > 0 && a.height > 0 && a.width < 600 && a.height < 600;
  }
  function nearRect(actor, rect, origin, margin = 110) {
    if (!validActor(actor)) return false;
    const cx = actor.x - origin.x + actor.width / 2;
    const cy = actor.y - origin.y + actor.height / 2;
    return cx >= rect.left - margin && cx <= rect.right + margin &&
      cy >= rect.top - margin && cy <= rect.bottom + margin;
  }
  function gridPosition(actor, origin, arenaRect) {
    const x = actor.x + actor.width / 2 - origin.x;
    const y = actor.y + actor.height / 2 - origin.y;
    return {
      x: Math.max(45, Math.min(arenaRect.width - 46, Math.round((x - arenaRect.left) / 44) * 44)),
      bottom: Math.max(18, Math.min(arenaRect.height - 85, Math.round((arenaRect.bottom - y) / 44) * 44)),
    };
  }
  function isNewAction(actor, sequence) {
    return validActor(actor) && ACTIONS.has(actor.action) &&
      Number.isSafeInteger(actor.event_id) && actor.event_id > sequence;
  }
  function validImage(value) {
    return typeof value === 'string' && value.length <= MAX_IMAGE &&
      /^data:image\/png;base64,[a-zA-Z0-9+/=]+$/.test(value);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {validActor, nearRect, gridPosition, isNewAction, validImage};
  }
  if (typeof document === 'undefined') return;

  const byId = id => document.getElementById(id);
  const arena = byId('arena');
  const blocks = byId('blocks');
  const message = byId('message');
  const lastSequence = new Map();
  let socket = null;
  let state = restore();
  let lastContact = null;
  let currentTexture = null;

  function restore() {
    try {
      const data = JSON.parse(localStorage.getItem(KEY));
      if (data && Array.isArray(data.blocks) && data.blocks.length <= MAX_BLOCKS &&
          Number.isInteger(data.mined) && data.mined >= 0 &&
          Number.isInteger(data.built) && data.built >= 0) {
        return {blocks: data.blocks.filter(b => typeof b.id === 'string' &&
          ['wood','stone','glass','moss','added'].includes(b.kind) &&
          Number.isFinite(b.x) && Number.isFinite(b.bottom)).slice(0, MAX_BLOCKS),
          mined: data.mined, built: data.built, impacts: 0};
      }
    } catch (_) { /* an invalid local snapshot returns the original arena */ }
    return {blocks: INITIAL.map(b => ({...b, bottom: 28, x: b.x, isPercent: true})),
      mined: 0, built: 0, impacts: 0};
  }
  function save() {
    try {localStorage.setItem(KEY, JSON.stringify({blocks: state.blocks, mined: state.mined,
      built: state.built}));} catch (_) { /* storage can be disabled; live play remains usable */ }
  }
  function status(text) { message.textContent = text; }
  function updateStats() {
    byId('blocks-mined').textContent = String(state.mined);
    byId('blocks-built').textContent = String(state.built);
    byId('impacts').textContent = String(state.impacts);
  }
  function renderBlock(block) {
    const el = document.createElement('div');
    el.className = `block ${block.kind}`;
    el.dataset.windowriftTarget = '';
    el.dataset.id = block.id;
    el.style.left = block.isPercent ? `${block.x}%` : `${block.x}px`;
    el.style.bottom = `${block.bottom}px`;
    const name = document.createElement('span');
    name.textContent = block.kind === 'added' ? 'MOVED FROM MC' : block.kind.toUpperCase();
    el.appendChild(name);
    if (block.kind === 'added' && validImage(block.texture)) {
      const sprite = document.createElement('img');
      sprite.src = block.texture;
      sprite.alt = 'Block captured from the running Minecraft window';
      el.insertBefore(sprite, name);
    }
    blocks.appendChild(el);
    return el;
  }
  function render() {
    blocks.replaceChildren();
    state.blocks.forEach(renderBlock);
    updateStats();
  }
  function viewportOrigin() {
    const side = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
    return {x: window.screenX + side,
      y: window.screenY + window.outerHeight - window.innerHeight - side};
  }
  function debris(element) {
    const r = element.getBoundingClientRect();
    const a = arena.getBoundingClientRect();
    const color = getComputedStyle(element).backgroundColor;
    for (let i = 0; i < 14; i++) {
      const chip = document.createElement('div');
      chip.className = 'chip';
      chip.style.backgroundColor = color;
      chip.style.left = `${r.left - a.left + r.width / 2}px`;
      chip.style.top = `${r.top - a.top + r.height / 2}px`;
      const dx = Math.round(Math.sin(i * 2.7) * (20 + i * 3));
      const dy = Math.round(Math.cos(i * 2.4) * 54 + i * 2);
      chip.style.setProperty('--dx', `${dx}px`);
      chip.style.setProperty('--dy', `${dy}px`);
      arena.appendChild(chip);
      setTimeout(() => chip.remove(), 800);
    }
  }
  function mine(actor, origin) {
    let chosen = null, best = Infinity;
    for (const el of blocks.children) {
      const rect = el.getBoundingClientRect();
      if (!nearRect(actor, rect, origin)) continue;
      const dx = actor.x + actor.width / 2 - origin.x - (rect.left + rect.width / 2);
      const dy = actor.y + actor.height / 2 - origin.y - (rect.top + rect.height / 2);
      const d = dx * dx + dy * dy;
      if (d < best) {best = d; chosen = el;}
    }
    if (!chosen) {status('Get closer to an HTML block, then press E.'); return;}
    const id = chosen.dataset.id;
    debris(chosen);
    chosen.classList.add('mined');
    chosen.remove();
    state.blocks = state.blocks.filter(b => b.id !== id);
    state.mined += 1;
    state.impacts += 1;
    status(`MINED: ${id}. That real DOM node is gone. Reload the page to check.`);
    save(); updateStats();
    arena.dispatchEvent(new CustomEvent('windowrift:mine', {detail: {id, actor: actor.id}}));
  }
  function place(actor, origin) {
    if (state.blocks.length >= MAX_BLOCKS) {status('The arena is full. Mine first.'); return;}
    if (!nearRect(actor, arena.getBoundingClientRect(), origin, 0)) {
      status('Move inside the browser arena before pressing F.'); return;
    }
    const point = gridPosition(actor, origin, arena.getBoundingClientRect());
    const id = `block-${state.built + 1}`;
    const texture = validImage(currentTexture) ? currentTexture : null;
    const entry = {id, kind: 'added', x: point.x, bottom: point.bottom,
      ...(texture ? {texture} : {})};
    state.blocks.push(entry);
    renderBlock(entry);
    state.built += 1;
    status(`PLACED: ${id}. A new HTML block now exists here.`);
    save(); updateStats();
    arena.dispatchEvent(new CustomEvent('windowrift:place', {detail: {id, actor: actor.id}}));
  }
  function onActors(actors) {
    const origin = viewportOrigin();
    for (const actor of actors.slice(0, 32)) {
      if (!validActor(actor)) continue;
      window.__riftLastActor = {id: actor.id, x: actor.x, y: actor.y,
        width: actor.width, height: actor.height};
      if (validImage(actor.texture)) currentTexture = actor.texture;
      const prev = lastSequence.get(actor.id) || 0;
      if (isNewAction(actor, prev)) {
        lastSequence.set(actor.id, actor.event_id);
        if (actor.action === 'mine') mine(actor, origin);
        if (actor.action === 'place') place(actor, origin);
      }
      const inArena = nearRect(actor, arena.getBoundingClientRect(), origin, 0);
      if (inArena && lastContact !== actor.id) {
        lastContact = actor.id;
        state.impacts += 1;
        updateStats();
      }
      if (!inArena && lastContact === actor.id) lastContact = null;
    }
  }
  function connect() {
    const token = byId('token').value.trim();
    if (token.length < 16) {byId('connection').textContent = 'A 16+ character token is required'; return;}
    if (socket) socket.close();
    const ws = new WebSocket(`ws://127.0.0.1:8765/?token=${encodeURIComponent(token)}`);
    socket = ws;
    ws.onopen = () => {
      byId('connection').textContent = 'Connected to WindowRift';
      byId('token').value = '';
      status('Use A/D to travel from Minecraft. E mines. F builds.');
    };
    ws.onerror = () => {byId('connection').textContent = 'Connection failed';};
    ws.onclose = () => {if (socket === ws) byId('connection').textContent = 'Disconnected';};
    ws.onmessage = event => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'actors' && Array.isArray(data.actors)) onActors(data.actors);
      } catch (_) { /* ignore malformed messages */ }
    };
  }
  byId('connect').addEventListener('click', connect);
  byId('reset').addEventListener('click', () => {
    localStorage.removeItem(KEY);
    state = {blocks: INITIAL.map(b => ({...b, bottom: 28, isPercent:true})),
      mined:0,built:0,impacts:0};
    lastContact = null; lastSequence.clear();
    render(); status('Original HTML blocks restored.');
  });
  render();
})(typeof globalThis === 'undefined' ? this : globalThis);
