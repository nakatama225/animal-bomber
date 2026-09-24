const fs=require('fs');
const src=fs.readFileSync(require('path').join(__dirname, '..', 'animal-bomber.html'),'utf8');
let code=[...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1])[0];
const noop=()=>{};const grad={addColorStop:noop};
const cs=new Proxy({},{get(_,k){if(k==='canvas')return{width:0,height:0};if(k==='measureText')return()=>({width:10});if(k==='createLinearGradient'||k==='createRadialGradient')return()=>grad;return()=>{}},set(){return true}});
const el=()=>({classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},style:{},appendChild(c){return c},innerHTML:'',textContent:'',onclick:null,getContext:()=>cs,width:0,height:0,addEventListener:noop});
const c=new Map();
global.window={addEventListener:noop};
global.document={getElementById(i){if(!c.has(i))c.set(i,el());return c.get(i)},createElement:el,addEventListener:noop,querySelector:el,querySelectorAll:()=>[]};
let VT=0;
global.performance={now:()=>VT};global.requestAnimationFrame=()=>0;global.cancelAnimationFrame=noop;
global.setInterval=()=>0;global.clearInterval=noop;global.setTimeout=()=>0;global.clearTimeout=noop;
code+='\nglobal.__X={startGame,CFG,get players(){return players},get grid(){return grid},get bombs(){return bombs},SOFT,EMPTY,HARD,isSolidFor,collides,movePlayer,spawnBomb,bombAt,update,canPhase,walkableFor,RADIUS,getSpeed};';
new Function(code)();
const X=global.__X;
Object.assign(X.CFG,{mode:'vs',hpP1:1,hpP2:1,hpCPU:1,sfx:false,bgm:false});
X.CFG.pick.p1='mole'; X.CFG.pick.p2='rabbit';
X.startGame();
const m=X.players[0], r=X.players[1];
// 盤面を空に
for(let y=1;y<X.grid.length-1;y++)for(let x=1;x<X.grid[0].length-1;x++) if(X.grid[y][x]===X.SOFT) X.grid[y][x]=X.EMPTY;
r.state='OUT';

console.log('=== もぐらの当たり判定を直接調べる ===');
m.cx=3.5; m.cy=1.5;
// (4,1) に他人の爆弾（もぐらは重なってないので ignore に入らない）
r.state='ALIVE'; r.cx=9.5; r.cy=9.5;
const b=X.spawnBomb(r,4,1); b.timer=99;
console.log('爆弾(4,1) あり:', !!X.bombAt(4,1));
console.log('isSolidFor(もぐら, 4,1) =', X.isSolidFor(m,4,1), '  ← true なら通れない');
console.log('collides(もぐら, 4.5,1.5) =', X.collides(m,4.5,1.5));
console.log('walkableFor(もぐら, 4,1) =', X.walkableFor(m,4,1));

// 実際に押し込んでみる
const step=(n,dt=1/60)=>{for(let i=0;i<n;i++){VT+=dt*1000;X.movePlayer(m,1,0,dt);}};
const x0=m.cx;
step(240);
console.log('右へ4秒押し続けた結果: cx', x0.toFixed(2), '→', m.cx.toFixed(2), ' (爆弾は x=4 のマス)');
console.log(m.cx < 4.0 ? '  ✅ 爆弾で止まってる（すり抜けてない）' : '  ❌ 爆弾をすり抜けた');

console.log('');
console.log('=== ソフトブロック経由の迂回も見る ===');
// (4,1) 爆弾、(4,0) は外壁。(4,2) を SOFT にして、そこ経由で通れるか
X.grid[2][4]=X.SOFT;
m.cx=3.5; m.cy=1.5;
console.log('isSolidFor(もぐら, 4,2=SOFT) =', X.isSolidFor(m,4,2), ' ← false なら通れる');
console.log('もぐらは SOFT を通れる:', X.canPhase(m));
console.log('→ 爆弾そのものは通れないが、隣が SOFT なら迂回できる');
