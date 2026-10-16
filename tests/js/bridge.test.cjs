const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '..', '..', 'browser-extension', 'content.js'), 'utf8');

function setup() {
  let listener;
  let now = 1000;
  const events = [];
  const sockets = [];
  const target = {
    isConnected: true,
    style: { transform: 'scale(1)', transition: 'opacity 0.1s', willChange: '' },
    matches: () => false,
    closest: selector => selector.includes('data-windowrift-target') ? target : null,
    getBoundingClientRect: () => ({ width: 80, height: 70, top: 10, left: 10, bottom: 80 }),
    hasAttribute: () => true,
    dispatchEvent: ev => events.push(ev),
  };
  class HTMLElement {}
  Object.setPrototypeOf(target, HTMLElement.prototype);
  class WebSocket {
    constructor(url) { this.url = url; sockets.push(this); }
    close() { this.closed = true; }
  }
  const ctx = {
    chrome: { runtime: { onMessage: { addListener: fn => { listener = fn; } } } },
    document: { elementsFromPoint: (x, y) => x >= 10 && x < 90 && y >= 10 && y < 80 ? [target] : [] },
    window: { screenX: 0, screenY: 0, outerWidth: 400, innerWidth: 400,
      outerHeight: 400, innerHeight: 400 },
    innerWidth: 400, innerHeight: 400,
    WebSocket, HTMLElement,
    CustomEvent: class { constructor(type, details) { this.type=type; Object.assign(this, details); } },
    performance: { now: () => now },
  };
  vm.runInNewContext(source, ctx);
  return { events, sockets, target, advanceClock: ms => { now += ms; }, onCommand: m => listener(m),
    send: (actors) => sockets.at(-1).onmessage({ data: JSON.stringify({type:'actors',actors}) }) };
}

test('explicit page targets receive one semantic event per actor entry', () => {
  const s = setup();
  s.onCommand({ type: 'WINDOWRIFT_START', token: 'secret-token' });
  assert.equal(s.sockets.length, 1);
  assert.match(s.sockets[0].url, /token=secret-token/);
  const actor = { id: 9, x: 10, y: 10, width: 30, height: 30 };
  s.send([actor]);
  s.send([actor]);
  assert.equal(s.events.length, 1);
  assert.equal(s.events[0].type, 'windowrift:impact');
  assert.equal(s.events[0].detail.id, 9);
  assert.match(s.target.style.transform, /translate/);
  s.send([{ ...actor, x: 300, y: 300 }]);
  s.advanceClock(300);
  s.send([actor]);
  assert.equal(s.events.length, 2);
  s.onCommand({ type: 'WINDOWRIFT_RESET' });
  assert.equal(s.target.style.transform, 'scale(1)');
  assert.equal(s.target.style.transition, 'opacity 0.1s');
  assert.equal(s.sockets[0].closed, true);
});

test('malformed actor payloads are ignored without changing DOM', () => {
  const s = setup();
  s.onCommand({type: 'WINDOWRIFT_START',token:'x'});
  s.send([{id: 'oops', x: 0, y: 0, width: 20, height: 20}]);
  s.send([{id: 1, x: Number.NaN, y: 0, width: 20, height: 20}]);
  assert.equal(s.events.length,0);
  assert.equal(s.target.style.transform,'scale(1)');
});

test('character feet trigger contact while center is outside the target', () => {
  const ctx=setup();
  ctx.onCommand({type:'WINDOWRIFT_START',token:'test-secret'});
  ctx.send([{id:6,x:-15,y:20,width:30,height:30}]);
  assert.equal(ctx.events.length,1);
  ctx.send([{id:6,x:-15,y:20,width:30,height:30}]);
  assert.equal(ctx.events.length,1);
});
