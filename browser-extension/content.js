(() => {
  if (globalThis.__windowriftBridgeInstalled) return;
  globalThis.__windowriftBridgeInstalled = true;

  let socket = null;
  let lastImpact = new WeakMap();
  const changed = new Map();
  const activeTargets = new Map();

  function reset() {
    if (socket) { socket.close(); socket = null; }
    for (const [el, styles] of changed) {
      if (!el.isConnected) continue;
      el.style.transform = styles.transform;
      el.style.transition = styles.transition;
      el.style.willChange = styles.willChange;
    }
    changed.clear();
    activeTargets.clear();
    lastImpact = new WeakMap();
  }

  function viewportTopLeft() {
    // Approximate at 100% scaling. Browser toolbars and window decorations vary.
    const side = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
    return {
      x: window.screenX + side,
      y: window.screenY + (window.outerHeight - window.innerHeight) - side
    };
  }

  function chooseTarget(x, y) {
    for (const hit of document.elementsFromPoint(x, y)) {
      if (!(hit instanceof HTMLElement)) continue;
      if (hit.matches('html, body, script, style, input, textarea, select, video, iframe, canvas')) continue;
      if (hit.closest('[contenteditable="true"], input, textarea, [role="textbox"]')) continue;
      // Pages that want app-state interactions explicitly opt in to an event.
      const tagged = hit.closest('[data-windowrift-target]');
      const element = tagged instanceof HTMLElement ? tagged : hit;
      const bounds = element.getBoundingClientRect();
      if (bounds.width < 14 || bounds.height < 12 || bounds.width > 520 || bounds.height > 320) continue;
      if (bounds.top < 0 || bounds.left < 0 || bounds.bottom > window.innerHeight) continue;
      return element;
    }
    return null;
  }

  function impact(actor) {
    if (!Number.isInteger(actor.id) || ![actor.x, actor.y, actor.width, actor.height].every(Number.isFinite)) return;
    if (actor.width <= 0 || actor.height <= 0) return;
    const origin = viewportTopLeft();
    const left = actor.x - origin.x, top = actor.y - origin.y;
    const probes = [
      [left + actor.width / 2, top + actor.height - 1],
      [left + actor.width - 1, top + actor.height - 1],
      [left + 1, top + actor.height - 1],
      [left + actor.width / 2, top + actor.height / 2],
    ];
    let element = null;
    for (const [x, y] of probes) {
      if (x >= 0 && x < innerWidth && y >= 0 && y < innerHeight) {
        element = chooseTarget(x, y);
        if (element) break;
      }
    }
    const previous = activeTargets.get(actor.id);
    if (element === null) {
      activeTargets.delete(actor.id);
      return;
    }
    if (previous === element) return; // One impact per entry, not one per frame.
    activeTargets.set(actor.id, element);
    const now = performance.now();
    if (now - (lastImpact.get(element) ?? -2000) < 250) return;
    lastImpact.set(element, now);
    if (changed.size >= 50 && !changed.has(element)) return;
    if (!changed.has(element)) {
      changed.set(element, {
        transform: element.style.transform,
        transition: element.style.transition,
        willChange: element.style.willChange
      });
    }
    const xShift = actor.id % 2 === 0 ? 15 : -15;
    const turn = actor.id % 2 === 0 ? 7 : -7;
    const original = changed.get(element).transform;
    element.style.transition = 'transform 440ms cubic-bezier(.2,.8,.2,1)';
    element.style.willChange = 'transform';
    element.style.transform = `${original} translate(${xShift}px, 10px) rotate(${turn}deg)`;

    // Opted-in pages can react in their own state without synthetic clicks.
    if (element.hasAttribute('data-windowrift-target')) {
      element.dispatchEvent(new CustomEvent('windowrift:impact', {
        bubbles: true,
        detail: { id: actor.id, x: actor.x, y: actor.y }
      }));
    }
  }

  chrome.runtime.onMessage.addListener(message => {
    if (message.type === 'WINDOWRIFT_RESET') { reset(); return; }
    if (message.type !== 'WINDOWRIFT_START') return;
    reset();
    const token = String(message.token || '');
    if (!token) return;
    socket = new WebSocket(`ws://127.0.0.1:8765/?token=${encodeURIComponent(token)}`);
    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data);
        if (message.type !== 'actors' || !Array.isArray(message.actors)) return;
        const seen = new Set();
        for (const actor of message.actors.slice(0, 128)) {
          impact(actor);
          seen.add(actor.id);
        }
        for (const id of activeTargets.keys()) if (!seen.has(id)) activeTargets.delete(id);
      } catch (_) { /* malformed local event: ignore */ }
    };
  });
})();
