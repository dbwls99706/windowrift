const test = require('node:test');
const assert = require('node:assert/strict');
const {validActor, nearRect, gridPosition, isNewAction, validImage} = require('../../examples/minecraft-rift.js');
const actor = {id:1,x:1000,y:650,width:50,height:50};
const origin = {x:825,y:180};

test('only finite, bounded desktop actor coordinates are accepted', () => {
  assert.equal(validActor(actor), true);
  assert.equal(validActor({...actor,width:Infinity}), false);
  assert.equal(validActor({...actor,id:'1'}), false);
  assert.equal(validActor({...actor,x:NaN}), false);
  assert.equal(validActor({...actor,height:-4}), false);
});
test('browser hit testing uses the real viewport-to-screen translation', () => {
  assert.equal(nearRect(actor, {left:140,right:230,top:410,bottom:540},origin,0),true);
  assert.equal(nearRect(actor, {left:10,right:80,top:20,bottom:60},origin,0),false);
});
test('same input event cannot mine the same block twice', () => {
  assert.equal(isNewAction({...actor,action:'mine',event_id:3},2),true);
  assert.equal(isNewAction({...actor,action:'mine',event_id:3},3),false);
  assert.equal(isNewAction({...actor,action:'place',event_id:4},3),true);
  assert.equal(isNewAction({...actor,action:'erase-disk',event_id:5},3),false);
});
test('block placement stays inside the HTML arena', () => {
  const point=gridPosition(actor,origin,{left:12,right:710,top:230,bottom:550,width:698,height:320});
  assert.ok(point.x>=45 && point.x<=652);
  assert.ok(point.bottom>=18 && point.bottom<=235);
});
test('source crop must be a bounded local PNG data URI', () => {
  assert.equal(validImage('data:image/png;base64,AAABBB=='),true);
  assert.equal(validImage('https://example.com/sprite.png'),false);
  assert.equal(validImage('data:image/svg+xml,<script>'),false);
  assert.equal(validImage('data:image/png;base64,'+'A'.repeat(75001)),false);
});
