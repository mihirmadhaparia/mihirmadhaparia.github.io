/* ============================================================
   MIHIR MADHAPARIA — site behavior (vanilla, no build step)
   ============================================================ */
(function () {
  'use strict';

  /* reveal on scroll */
  function initReveal() {
    var els = document.querySelectorAll('[data-reveal]');
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('IntersectionObserver' in window)) {
      for (var i = 0; i < els.length; i++) els[i].classList.add('is-in');
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  /* red magnetic cursor trail */
  function initCursorTrail() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;
    var N = 8, dots = [], i;
    for (i = 0; i < N; i++) {
      var d = document.createElement('div');
      d.style.cssText = 'position:fixed;width:8px;height:8px;background:#ff3b1d;z-index:9999;pointer-events:none;left:0;top:0;opacity:0;';
      document.body.appendChild(d);
      dots.push({ el: d, x: 0, y: 0 });
    }
    var mx = 0, my = 0, active = false;
    window.addEventListener('pointermove', function (e) { mx = e.clientX; my = e.clientY; active = true; }, { passive: true });
    (function loop() {
      var px = mx, py = my;
      for (var k = 0; k < dots.length; k++) {
        var dt = dots[k], s = 1 - k / N;
        dt.x += (px - dt.x) * 0.35; dt.y += (py - dt.y) * 0.35;
        dt.el.style.transform = 'translate(' + (dt.x - 4) + 'px,' + (dt.y - 4) + 'px) scale(' + s + ')';
        dt.el.style.opacity = active ? (0.7 * s) : 0;
        px = dt.x; py = dt.y;
      }
      requestAnimationFrame(loop);
    })();
  }

  /* interactive magnetic vector-flow field (home hero) */
  function initFlow() {
    var c = document.getElementById('home-flow');
    if (!c) return;
    var ctx = c.getContext('2d');
    var W, H, dpr, cols, rows, gap = 24;
    var mouse = { x: -999, y: -999 };
    var pulse = 0, t = 0;
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      var r = c.getBoundingClientRect(); W = r.width; H = r.height;
      c.width = W * dpr; c.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(W / gap); rows = Math.ceil(H / gap);
    }
    resize();
    window.addEventListener('resize', resize, { passive: true });
    c.addEventListener('pointermove', function (e) { var r = c.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; });
    c.addEventListener('pointerleave', function () { mouse.x = -999; mouse.y = -999; });
    c.addEventListener('pointerdown', function () { pulse = 1; });
    (function loop() {
      t += 0.006; pulse *= 0.94;
      ctx.clearRect(0, 0, W, H);
      var R = 130 + pulse * 90;
      for (var i = 0; i <= cols; i++) {
        for (var j = 0; j <= rows; j++) {
          var x = i * gap + gap / 2, y = j * gap + gap / 2;
          var a = Math.sin(x * 0.012 + t) + Math.cos(y * 0.014 - t * 0.8) + Math.sin((x + y) * 0.006 + t * 1.3);
          var len = 8, col = 'rgba(233,231,225,0.5)', lw = 1;
          var dx = x - mouse.x, dy = y - mouse.y, dist = Math.hypot(dx, dy);
          if (dist < R) {
            var infl = 1 - dist / R;
            var swirl = Math.atan2(dy, dx) + Math.PI / 2;
            a = a * (1 - infl) + swirl * infl * 2.2;
            len = 8 + infl * (14 + pulse * 16);
            var kk = Math.min(1, infl * 1.4 + pulse * 0.5);
            col = 'rgba(255,' + Math.round(59 + (233 - 59) * (1 - kk)) + ',' + Math.round(29 + (225 - 29) * (1 - kk)) + ',' + (0.5 + infl * 0.5) + ')';
            lw = 1.6;
          }
          var ca = Math.cos(a) * len, sa = Math.sin(a) * len;
          ctx.strokeStyle = col; ctx.lineWidth = lw;
          ctx.beginPath(); ctx.moveTo(x - ca / 2, y - sa / 2); ctx.lineTo(x + ca / 2, y + sa / 2); ctx.stroke();
        }
      }
      requestAnimationFrame(loop);
    })();
  }

  /* count-up stats */
  function initCounts() {
    var els = document.querySelectorAll('[data-count]');
    if (!els.length) return;
    function run(el) {
      var target = parseFloat(el.getAttribute('data-count')), t0 = performance.now(), dur = 1100;
      (function step(now) {
        var p = Math.min((now - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * e).toLocaleString();
        if (p < 1) requestAnimationFrame(step);
      })(t0);
    }
    if (!('IntersectionObserver' in window)) { for (var i = 0; i < els.length; i++) run(els[i]); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { run(en.target); io.unobserve(en.target); } });
    }, { threshold: 0.4 });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  /* weekly mileage chart (Beyond). Reads JSON from #week-data if present,
     otherwise renders placeholder data. Replace #week-data with your Strava totals. */
  function initWeekChart() {
    var host = document.getElementById('week-chart');
    if (!host) return;
    var readout = document.getElementById('wk-readout');
    var data;
    var dataEl = document.getElementById('week-data');
    if (dataEl) {
      try { data = JSON.parse(dataEl.textContent); } catch (e) { data = null; }
    }
    if (!data || !data.length) {
      data = [];
      for (var i = 0; i < 52; i++) {
        var base = 18 + 14 * Math.sin(i / 6) + (i / 52) * 12;
        var noise = (Math.sin(i * 2.3) + Math.cos(i * 1.7)) * 4;
        var v = Math.max(0, base + noise);
        if (i % 13 === 12) v *= 0.45;
        data.push(Math.round(v));
      }
    }
    var max = Math.max.apply(null, data);
    data.forEach(function (v, i) {
      var bar = document.createElement('div');
      bar.className = 'bar';
      bar.style.height = (max ? (v / max) * 100 : 0) + '%';
      bar.addEventListener('pointerenter', function () { if (readout) readout.textContent = 'WEEK -' + (52 - i) + ' \u00b7 ' + v + ' MI'; });
      host.appendChild(bar);
    });
  }

  /* photo hover captions (Beyond) — caption text lives in data-cap */
  function initPhotoCaps() {
    var photos = document.querySelectorAll('.photo[data-cap]');
    for (var i = 0; i < photos.length; i++) {
      var w = photos[i];
      if (w.querySelector('.photo__cap')) continue;
      var cap = document.createElement('div');
      cap.className = 'photo__cap';
      cap.textContent = w.getAttribute('data-cap') || '';
      w.appendChild(cap);
    }
  }

  /* mobile nav */
  function initNav() {
    var t = document.querySelector('.b-nav-toggle'), nav = document.getElementById('b-nav');
    if (!t || !nav) return;
    t.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      t.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  /* ---------- skills: a UNIQUE playful reaction per skill (no repeats) ---------- */
  function initSkillReactions() {
    var grid = document.querySelector('.skillgrid');
    if (!grid) return;
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var canAnim = typeof Element !== 'undefined' && Element.prototype.animate;
    var PAL = ['#ff3b1d', '#111111', '#f4b400', '#1d6dff', '#17a06b', '#7b3ff2'];

    function spark(css){var d=document.createElement('div');d.style.cssText='position:fixed;left:0;top:0;pointer-events:none;z-index:9998;will-change:transform,opacity;font-family:var(--font-display),sans-serif;'+css;document.body.appendChild(d);return d;}
    function fin(a,d){a.onfinish=function(){ if(d&&d.remove) d.remove(); };}
    function T(x,y,extra){return 'translate('+x+'px,'+y+'px)'+(extra||'');}

    var FX = {
      confetti:function(pill,cx,cy,g,c){for(var i=0;i<22;i++){var col=(i%3===0)?c:PAL[i%PAL.length];var d=spark('width:7px;height:12px;background:'+col+';');var ang=Math.random()*6.283,sp=70+Math.random()*150,dx=Math.cos(ang)*sp,dy=Math.sin(ang)*sp-80;fin(d.animate([{transform:T(cx,cy)+' rotate(0)',opacity:1},{transform:T(cx+dx,cy+dy+210)+' rotate('+(720*(Math.random()-0.5))+'deg)',opacity:0}],{duration:1000+Math.random()*500,easing:'cubic-bezier(.2,.6,.2,1)'}),d);}},
      firework:function(pill,cx,cy,g,c){for(var i=0;i<20;i++){var a=(i/20)*6.283,sp=90+Math.random()*40,col=(i%2)?c:'#fff';var d=spark('width:6px;height:6px;border-radius:50%;background:'+col+';box-shadow:0 0 6px '+c+';');fin(d.animate([{transform:T(cx,cy)+' scale(1)',opacity:1},{transform:T(cx+Math.cos(a)*sp,cy+Math.sin(a)*sp+36)+' scale(.3)',opacity:0}],{duration:850,easing:'cubic-bezier(.15,.7,.3,1)'}),d);}},
      squares:function(pill,cx,cy,g,c){for(var i=0;i<14;i++){var a=Math.random()*6.283,sp=55+Math.random()*95;var d=spark('width:10px;height:10px;background:'+c+';');fin(d.animate([{transform:T(cx,cy)+' rotate(0)',opacity:1},{transform:T(cx+Math.cos(a)*sp,cy+Math.sin(a)*sp)+' rotate(220deg)',opacity:0}],{duration:560,easing:'ease-out'}),d);}},
      spiral:function(pill,cx,cy,g,c){for(var i=0;i<26;i++){var a=i*0.5,r=i*4;var d=spark('width:6px;height:6px;border-radius:50%;background:'+c+';');fin(d.animate([{transform:T(cx,cy)+' scale(1)',opacity:0.9},{transform:T(cx+Math.cos(a)*r,cy+Math.sin(a)*r)+' scale(.2)',opacity:0}],{duration:900,delay:i*12,easing:'ease-out'}),d);}},
      sparkle:function(pill,cx,cy,g,c){for(var i=0;i<12;i++){var glyph=(i%2)?g:'✦';var d=spark('font-size:'+(14+Math.random()*14)+'px;color:'+c+';');d.textContent=glyph;var ox=(Math.random()-.5)*120,oy=(Math.random()-.5)*70;fin(d.animate([{transform:T(cx+ox,cy+oy)+' scale(0)',opacity:0},{transform:T(cx+ox,cy+oy-10)+' scale(1.2)',opacity:1,offset:.4},{transform:T(cx+ox,cy+oy-24)+' scale(0)',opacity:0}],{duration:800+Math.random()*400,delay:i*30}),d);}},
      ring:function(pill,cx,cy,g,c){var d=spark('width:26px;height:26px;border:3px solid '+c+';border-radius:50%;');fin(d.animate([{transform:T(cx-13,cy-13)+' scale(.2)',opacity:.9},{transform:T(cx-13,cy-13)+' scale(6)',opacity:0}],{duration:640,easing:'ease-out'}),d);},
      rings3:function(pill,cx,cy,g,c){for(var i=0;i<3;i++){var d=spark('width:26px;height:26px;border:3px solid '+c+';border-radius:50%;');fin(d.animate([{transform:T(cx-13,cy-13)+' scale(.2)',opacity:.85},{transform:T(cx-13,cy-13)+' scale(6)',opacity:0}],{duration:800,delay:i*150,easing:'ease-out'}),d);}},
      beam:function(pill,cx,cy,g,c){var d=spark('width:10px;height:170px;background:linear-gradient(180deg,'+c+',transparent);transform-origin:bottom center;');fin(d.animate([{transform:T(cx-5,cy-170)+' scaleY(0)',opacity:0},{transform:T(cx-5,cy-170)+' scaleY(1)',opacity:1,offset:.3},{transform:T(cx-5,cy-170)+' scaleY(1)',opacity:0}],{duration:650,easing:'ease-out'}),d);},
      floatUp:function(pill,cx,cy,g,c){for(var i=0;i<4;i++){var d=spark('font-size:'+(20+Math.random()*12)+'px;');d.textContent=g;var ox=(Math.random()-.5)*40;fin(d.animate([{transform:T(cx+ox,cy)+' scale(.6)',opacity:0},{transform:T(cx+ox,cy-70)+' scale(1.15)',opacity:1,offset:.3},{transform:T(cx+ox,cy-170)+' scale(1)',opacity:0}],{duration:1150,delay:i*90,easing:'ease-out'}),d);}},
      fountain:function(pill,cx,cy,g,c){for(var i=0;i<10;i++){var d=spark('font-size:'+(16+Math.random()*12)+'px;');d.textContent=g;var vx=(Math.random()-.5)*160;fin(d.animate([{transform:T(cx,cy)+' scale(.5)',opacity:0},{transform:T(cx+vx*0.5,cy-120-Math.random()*40)+' scale(1.1)',opacity:1,offset:.4},{transform:T(cx+vx,cy+120)+' scale(.8)',opacity:0}],{duration:1200,easing:'cubic-bezier(.2,.5,.5,1)'}),d);}},
      rain:function(pill,cx,cy,g,c){var r=pill.getBoundingClientRect();for(var i=0;i<9;i++){var d=spark('font-size:'+(16+Math.random()*10)+'px;');d.textContent=g;var x=r.left+Math.random()*r.width;fin(d.animate([{transform:T(x,r.top-30)+' scale(.7)',opacity:0},{transform:T(x,r.top-10)+' scale(1)',opacity:1,offset:.15},{transform:T(x,r.bottom+70)+' scale(1)',opacity:0}],{duration:1000,delay:i*70,easing:'cubic-bezier(.4,0,.7,1)'}),d);}},
      orbit:function(pill,cx,cy,g,c){var R=48;for(var k=0;k<4;k++){var d=spark('font-size:22px;');d.textContent=g;var kf=[],st=k*(6.283/4);for(var s2=0;s2<=14;s2++){var a=st+(s2/14)*6.283;kf.push({transform:T(cx+Math.cos(a)*R-11,cy+Math.sin(a)*R-11)+' scale(1)',opacity:s2===0?0:(s2>=13?0:1)});}fin(d.animate(kf,{duration:1000,easing:'linear'}),d);}},
      bigDrop:function(pill,cx,cy,g,c){var d=spark('font-size:54px;');d.textContent=g;fin(d.animate([{transform:T(cx-22,cy-190)+' scale(1)',opacity:0},{transform:T(cx-22,cy-30)+' scale(1)',opacity:1,offset:.45},{transform:T(cx-22,cy-52)+' scale(1)',offset:.62},{transform:T(cx-22,cy-30)+' scale(1)',offset:.78},{transform:T(cx-22,cy-40)+' scale(1)',opacity:0}],{duration:1100,easing:'cubic-bezier(.3,.8,.4,1)'}),d);},
      stamp:function(pill,cx,cy,g,c){var d=spark('font-size:46px;color:'+c+';font-weight:800;');d.textContent=g;var b=T(cx-22,cy-34,' rotate(-12deg) ');fin(d.animate([{transform:b+'scale(2.7)',opacity:0},{transform:b+'scale(1)',opacity:1,offset:.25},{transform:b+'scale(1)',opacity:1,offset:.7},{transform:b+'scale(1.12)',opacity:0}],{duration:820}),d);},
      word:function(pill,cx,cy,g,c,t){var d=spark('font-weight:800;font-size:30px;color:#fff;-webkit-text-stroke:2px '+c+';letter-spacing:-.02em;');d.textContent=t||g;fin(d.animate([{transform:T(cx,cy-20)+' scale(.3) rotate(-8deg)',opacity:0},{transform:T(cx,cy-46)+' scale(1.25) rotate(-8deg)',opacity:1,offset:.3},{transform:T(cx,cy-80)+' scale(1) rotate(-8deg)',opacity:0}],{duration:950,easing:'cubic-bezier(.2,.7,.2,1)'}),d);},
      spin:function(pill,cx,cy,g,c){pill.animate([{transform:'rotate(0) scale(1)'},{transform:'rotate(360deg) scale(1.2)',offset:.6},{transform:'rotate(360deg) scale(1)'}],{duration:640,easing:'cubic-bezier(.2,.7,.2,1)'});FX.sparkle(pill,cx,cy,g,c);},
      flip:function(pill,cx,cy,g,c){pill.style.transformStyle='preserve-3d';pill.animate([{transform:'perspective(400px) rotateX(0) scale(1)'},{transform:'perspective(400px) rotateX(360deg) scale(1.12)',offset:.6},{transform:'perspective(400px) rotateX(360deg) scale(1)'}],{duration:700,easing:'cubic-bezier(.2,.7,.2,1)'});},
      glitch:function(pill,cx,cy,g,c){var kf=[];for(var i=0;i<6;i++)kf.push({transform:'translate('+((Math.random()-.5)*10)+'px,'+((Math.random()-.5)*6)+'px)',filter:'hue-rotate('+(i*55)+'deg) saturate(2.2)'});kf.push({transform:'none',filter:'none'});pill.animate(kf,{duration:440,easing:'steps(6)'});},
      shake:function(pill,cx,cy,g,c){pill.animate([{transform:'translateX(0)'},{transform:'translateX(-7px) rotate(-3deg)'},{transform:'translateX(6px) rotate(3deg)'},{transform:'translateX(-5px) rotate(-2deg)'},{transform:'translateX(4px)'},{transform:'translateX(0)'}],{duration:480,easing:'ease-in-out'});FX.firework(pill,cx,cy,g,c);}
    };

    // one distinct reaction per skill: [effect, glyph, color, optional word]
    var REG = {
      'ansys':['rings3','🔥','#ff3b1d'],
      'autocad':['spiral','📐','#1d6dff'],
      'autodesk fusion':['flip','🧊','#1d6dff'],
      'civil3d':['floatUp','🛣️','#f4b400'],
      'ptc creo':['orbit','🛠️','#17a06b'],
      'tekla structures':['rain','🏗️','#f4b400'],
      'solidworks':['spin','🔧','#ff3b1d'],
      'siemens nx':['squares','🧩','#7b3ff2'],
      'epanet':['fountain','💧','#1d6dff'],
      'arcgis':['bigDrop','📍','#ff3b1d'],
      'matlab':['beam','📈','#f4b400'],
      'python':['fountain','🐍','#17a06b'],
      'javascript':['sparkle','⚡','#f4b400'],
      'java':['floatUp','☕','#8a5a2b'],
      'c and c++':['orbit','⚙️','#111111'],
      'r':['confetti','📊','#17a06b'],
      'html':['glitch','🌐','#1d6dff'],
      'g-code':['spiral','🖨️','#111111'],
      'ruby':['sparkle','💎','#e0245e'],
      'mts elite':['shake','🧪','#7b3ff2'],
      'power bi':['confetti','💹','#f4b400'],
      'ptc windchill':['ring','🌀','#1d6dff'],
      'materialise mimics':['stamp','🦴','#111111'],
      'minitab':['beam','📉','#ff3b1d'],
      'imagej':['ring','🔬','#17a06b'],
      'microsoft suite':['squares','🪟','#1d6dff'],
      'design verification':['stamp','✔️','#17a06b'],
      'test method validation':['rain','🧾','#111111'],
      'design assurance':['rings3','🛡️','#1d6dff'],
      'fmea & risk analysis':['word','⚠️','#ff3b1d','RISK!'],
      'complaint investigation':['bigDrop','🔎','#7b3ff2'],
      'fda 21 cfr part 820':['word','📋','#ff3b1d','FDA'],
      'iso 13485':['flip','✅','#17a06b'],
      'iso 14971':['firework','🎯','#ff3b1d'],
      'eu mdr':['firework','🇪🇺','#1d6dff'],
      'design of experiments':['glitch','🧫','#7b3ff2']
    };

    function hash(str){var h=0;for(var i=0;i<str.length;i++){h=(h*31+str.charCodeAt(i))>>>0;}return h;}
    function flash(pill,c){pill.animate([{backgroundColor:'#e9e7e1'},{backgroundColor:c,color:'#fff',offset:.3},{backgroundColor:'#e9e7e1',color:'#111'}],{duration:600});}
    function pressPop(pill){ if(canAnim) pill.animate([{transform:'scale(.92)'},{transform:'scale(1)'}],{duration:170,easing:'ease-out'}); }

    function react(pill){
      var key=(pill.textContent||'').trim().toLowerCase();
      var r=pill.getBoundingClientRect(), cx=r.left+r.width/2, cy=r.top+r.height/2;
      var e=REG[key];
      pressPop(pill);
      if(reduce||!canAnim){ if(e) flash(pill,e[2]); return; }
      if(e && FX[e[0]]){ FX[e[0]](pill,cx,cy,e[1],e[2],e[3]); }
      else { var names=Object.keys(FX), n=names[hash(key)%names.length]; FX[n](pill,cx,cy,'✦',PAL[hash(key)%PAL.length]); }
    }

    var pills=grid.querySelectorAll('.pill');
    for(var i=0;i<pills.length;i++){ pills[i].setAttribute('tabindex','0'); pills[i].setAttribute('role','button'); }
    grid.addEventListener('click',function(e){var p=e.target.closest('.pill'); if(p) react(p);});
    grid.addEventListener('keydown',function(e){ if(e.key!=='Enter'&&e.key!==' ')return; var p=e.target.closest('.pill'); if(p){e.preventDefault();react(p);} });
  }

  function init() {
    initNav();
    initReveal();
    initCursorTrail();
    initFlow();
    initCounts();
    initWeekChart();
    initPhotoCaps();
    initSkillReactions();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
