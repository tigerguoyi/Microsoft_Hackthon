import {resolvePlayer} from './player-identity.js';
// Shared Replay/Decision canvas renderer. Palette and geometry inherited from 96d13a.
export function pitchGeometry(canvasWidth, canvasHeight) {
  const w = canvasWidth, h = canvasHeight;
  const scale = Math.min((w - 42) / 105, (h - 69) / 68);
  return { x: (w - 105 * scale) / 2, y: (h - 68 * scale) / 2 + 3, scale, w, h };
}

export function renderPitch(canvas, frame, {metadata, selected=null, route=null, actualRoute=null, width, height}={}) {  if (!canvas || !frame) return;
  const canvasWidth=width||canvas.clientWidth, canvasHeight=height||canvas.clientHeight;
  if (!canvasWidth||!canvasHeight) return;
  const ratio=Math.min(globalThis.devicePixelRatio||1,2);
  if(canvas.width!==Math.round(canvasWidth*ratio))canvas.width=Math.round(canvasWidth*ratio);
  if(canvas.height!==Math.round(canvasHeight*ratio))canvas.height=Math.round(canvasHeight*ratio);
  const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);
  const numberOf=id=>resolvePlayer(metadata,id).jersey_number??'?';
  const { x, y, scale: s, w, h } = pitchGeometry(canvasWidth,canvasHeight);
  const X = v => x + v * s, Y = v => y + v * s;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#426e57'; ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < 10; i++) { ctx.fillStyle = i % 2 ? '#47745c' : '#426e57'; ctx.fillRect(X(i * 10.5), y, 10.5 * s, 68 * s); }
  ctx.strokeStyle = '#b9d1bd80'; ctx.lineWidth = 1;
  const rect = (a, b, c, d) => ctx.strokeRect(X(a), Y(b), c * s, d * s);
  const circle = (a, b, r, start = 0, end = Math.PI * 2) => { ctx.beginPath(); ctx.arc(X(a), Y(b), r * s, start, end); ctx.stroke(); };
  rect(0, 0, 105, 68); rect(0, 13.84, 16.5, 40.32); rect(88.5, 13.84, 16.5, 40.32);
  rect(0, 24.84, 5.5, 18.32); rect(99.5, 24.84, 5.5, 18.32);
  rect(-2.2, 30.34, 2.2, 7.32); rect(105, 30.34, 2.2, 7.32);
  ctx.beginPath(); ctx.moveTo(X(52.5), Y(0)); ctx.lineTo(X(52.5), Y(68)); ctx.stroke();
  circle(52.5, 34, 9.15); circle(11, 34, 9.15, -.924, .924); circle(94, 34, 9.15, Math.PI - .924, Math.PI + .924);
  circle(0, 0, 1, 0, Math.PI / 2); circle(105, 0, 1, Math.PI / 2, Math.PI); circle(0, 68, 1, -Math.PI / 2, 0); circle(105, 68, 1, Math.PI, Math.PI * 1.5);
  ctx.fillStyle = '#c2d8c4a0';
  for (const px of [11, 52.5, 94]) { ctx.beginPath(); ctx.arc(X(px), Y(34), 1.6, 0, Math.PI * 2); ctx.fill(); }
  for(const [r,dashed,color] of [[actualRoute,false,'#fff6dc'],[route,true,'#f7cc78']]) {
    if(!r)continue;
    ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash(dashed?[7,5]:[]);
    ctx.moveTo(X(r.start[0]),Y(r.start[1]));ctx.lineTo(X(r.target[0]),Y(r.target[1]));ctx.stroke();ctx.setLineDash([]);
    const a=Math.atan2(r.target[1]-r.start[1],r.target[0]-r.start[0]),tx=X(r.target[0]),ty=Y(r.target[1]);
    ctx.beginPath();ctx.moveTo(tx-8*Math.cos(a-.4),ty-8*Math.sin(a-.4));ctx.lineTo(tx,ty);ctx.lineTo(tx-8*Math.cos(a+.4),ty-8*Math.sin(a+.4));ctx.stroke();
  }
  if(route?.recipient_id){
    const receiver=frame.players.find(p=>p[0]===route.recipient_id);
    const tx=X(route.target[0]),ty=Y(route.target[1]);
    if(receiver){ctx.beginPath();ctx.strokeStyle='#f7cc78';ctx.lineWidth=1;ctx.setLineDash([2,3]);ctx.moveTo(X(receiver[1]),Y(receiver[2]));ctx.lineTo(tx,ty);ctx.stroke();ctx.setLineDash([]);}
  }
  const radius = Math.max(6, Math.min(10, s * 1.65));
  for (const p of frame.players) {
    const identity=resolvePlayer(metadata,p[0]);
    const home = identity.team_id === 'HOME', isSelected = p[0] === selected, owner = p[0] === frame.ball_owner_id;
    const receiver = p[0] === route?.recipient_id;
    const px = X(p[1]), py = Y(p[2]);
    if (isSelected || owner) { ctx.beginPath(); ctx.arc(px, py, radius + (isSelected ? 4 : 2.5), 0, Math.PI * 2); ctx.strokeStyle = isSelected ? '#ffffffbc' : '#f9dc9c'; ctx.lineWidth = isSelected ? 1.4 : 1; ctx.stroke(); }
    if(receiver){ctx.beginPath();ctx.arc(px,py,radius+6,0,Math.PI*2);ctx.strokeStyle='#f7cc78';ctx.lineWidth=2;ctx.stroke();}
    ctx.shadowColor = '#183b3a65'; ctx.shadowBlur = 4; ctx.shadowOffsetY = 2;
    ctx.beginPath(); ctx.arc(px, py, radius, 0, Math.PI * 2); ctx.fillStyle = home ? '#ee8b5a' : '#83a3e0'; ctx.fill();
    ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    ctx.strokeStyle = home ? '#ffc9a391' : '#c5d7fbb0'; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = home ? '#fff7ed' : '#fff'; ctx.font = `600 ${Math.max(7, radius * .9)}px -apple-system, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(numberOf(p[0]), px, py + .4);
  }
  // Draw the receiving marker after player discs so a short lead cannot hide it.
  if(route?.recipient_id){const tx=X(route.target[0]),ty=Y(route.target[1]);ctx.beginPath();ctx.strokeStyle='#f7cc78';ctx.lineWidth=2;
    ctx.moveTo(tx,ty-6);ctx.lineTo(tx+6,ty);ctx.lineTo(tx,ty+6);ctx.lineTo(tx-6,ty);ctx.closePath();ctx.stroke();}
  const bx = X(frame.ball[0]), by = Y(frame.ball[1]), lift = Math.min(frame.ball[2] * s, 15);
  ctx.fillStyle = '#193d3760'; ctx.beginPath(); ctx.ellipse(bx + 1, by + 2, 3.5, 2, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(bx, by - lift, 3.6, 0, Math.PI * 2); ctx.fillStyle = '#fffdf4'; ctx.fill(); ctx.strokeStyle = '#e1d9bf'; ctx.lineWidth = .8; ctx.stroke();
  ctx.beginPath(); ctx.arc(bx, by - lift, 1.3, 0, Math.PI * 2); ctx.fillStyle = '#707c6d'; ctx.fill();
}

// Which player is under the pointer. The circle radius is what renderPitch
// draws, plus a few pixels of slop so a small canvas is still clickable.
export function hitTestPlayer(canvas, frame, {clientX, clientY}={}) {
  if (!canvas || !frame || !frame.players) return null;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return null;
  const rect = canvas.getBoundingClientRect();
  const px = clientX - rect.left, py = clientY - rect.top;
  const { x, y, scale: s } = pitchGeometry(width, height);
  if(route?.recipient_id){
    const receiver=frame.players.find(p=>p[0]===route.recipient_id);
    const tx=X(route.target[0]),ty=Y(route.target[1]);
    if(receiver){ctx.beginPath();ctx.strokeStyle='#f7cc78';ctx.lineWidth=1;ctx.setLineDash([2,3]);ctx.moveTo(X(receiver[1]),Y(receiver[2]));ctx.lineTo(tx,ty);ctx.stroke();ctx.setLineDash([]);}
  }
  const radius = Math.max(6, Math.min(10, s * 1.65));
  let nearest = null, nearestDistance = radius + 6;
  for (const player of frame.players) {
    const distance = Math.hypot(x + player[1] * s - px, y + player[2] * s - py);
    if (distance < nearestDistance) { nearestDistance = distance; nearest = player[0]; }
  }
  return nearest;
}

// Whether a click landed on the pitch surface rather than outside it.
export function hitTestPitch(canvas, {clientX, clientY}={}) {
  if (!canvas) return false;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return false;
  const rect = canvas.getBoundingClientRect();
  const px = clientX - rect.left, py = clientY - rect.top;
  const { x, y, scale: s } = pitchGeometry(width, height);
  return px >= x && px <= x + 105 * s && py >= y && py <= y + 68 * s;
}
