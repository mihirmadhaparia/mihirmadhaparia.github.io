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

  /* ---------- skills: unique playful click reaction per skill ---------- */
  function initSkillReactions() {
    var grid = document.querySelector('.skillgrid');
    if (!grid) return;
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var canAnim = typeof Element !== 'undefined' && Element.prototype.animate;
    var PALETTE = ['#ff3b1d', '#111111', '#e9e7e1', '#f4b400', '#1d6dff'];
    var WORDS = ['POW', 'ZAP', 'BAM', 'BOOM', 'WHAM', 'ZING', 'YEAH', 'NICE'];
    // themed glyph for recognizable skills; others fall back to a fun set
    var THEME = {
      'python':'🐍','r':'📈','matlab':'📉','javascript':'⚡','java':'☕',
      'html':'</>','ruby':'💎','c and c++':'⚙️','g-code':'⟿','solidworks':'🔧',
      'ansys':'🔥','autocad':'📐','ptc creo':'🛠️','siemens nx':'🧩',
      'autodesk fusion':'🧊','tekla structures':'🏗️','civil3d':'🛣️',
      'epanet':'🚰','arcgis':'🗺️','power bi':'📊','minitab':'📉',
      'imagej':'🔬','materialise mimics':'🦴','ptc windchill':'🌀','mts elite':'🧪',
      'microsoft suite':'🪟','fmea & risk analysis':'⚠️','iso 13485':'✅','iso 14971':'✅',
      'eu mdr':'🇪🇺','fda 21 cfr part 820':'§','design verification':'✔️',
      'test method validation':'🧾','design assurance':'🛡️','complaint investigation':'🔎',
      'design of experiments':'🧫'
    };
    var FUN = ['✦','✵','◈','▲','●','❖','✻','✹'];

    function hash(str){var h=0;for(var i=0;i<str.length;i++){h=(h*31+str.charCodeAt(i))>>>0;}return h;}
    function spark(css){var d=document.createElement('div');d.style.cssText='position:fixed;left:0;top:0;pointer-events:none;z-index:9998;'+css;document.body.appendChild(d);return d;}
    function end(d){return function(){ if(d&&d.remove) d.remove(); };}

    function confetti(cx,cy){for(var i=0;i<20;i++){var col=PALETTE[i%PALETTE.length];var d=spark('width:7px;height:11px;background:'+col+';');var ang=Math.random()*Math.PI*2,sp=70+Math.random()*150;var dx=Math.cos(ang)*sp,dy=Math.sin(ang)*sp-70;d.animate([{transform:'translate('+cx+'px,'+cy+'px) rotate(0)',opacity:1},{transform:'translate('+(cx+dx)+'px,'+(cy+dy+200)+'px) rotate('+(720*(Math.random()-0.5))+'deg)',opacity:0}],{duration:900+Math.random()*500,easing:'cubic-bezier(.2,.6,.2,1)'}).onfinish=end(d);}}
    function shockwave(cx,cy){var d=spark('width:24px;height:24px;border:3px solid #ff3b1d;border-radius:50%;');d.animate([{transform:'translate('+(cx-12)+'px,'+(cy-12)+'px) scale(.2)',opacity:.9},{transform:'translate('+(cx-12)+'px,'+(cy-12)+'px) scale(6)',opacity:0}],{duration:600,easing:'ease-out'}).onfinish=end(d);}
    function firework(cx,cy){for(var i=0;i<16;i++){var a=(i/16)*Math.PI*2,sp=90+Math.random()*40;var d=spark('width:6px;height:6px;border-radius:50%;background:'+PALETTE[i%PALETTE.length]+';');d.animate([{transform:'translate('+cx+'px,'+cy+'px) scale(1)',opacity:1},{transform:'translate('+(cx+Math.cos(a)*sp)+'px,'+(cy+Math.sin(a)*sp+40)+'px) scale(.3)',opacity:0}],{duration:800,easing:'cubic-bezier(.15,.7,.3,1)'}).onfinish=end(d);}}
    function squares(cx,cy){for(var i=0;i<12;i++){var a=Math.random()*Math.PI*2,sp=50+Math.random()*90;var d=spark('width:9px;height:9px;background:#111;');d.animate([{transform:'translate('+cx+'px,'+cy+'px) rotate(0)',opacity:1},{transform:'translate('+(cx+Math.cos(a)*sp)+'px,'+(cy+Math.sin(a)*sp)+'px) rotate(180deg)',opacity:0}],{duration:520,easing:'ease-out'}).onfinish=end(d);}}
    function glyphPop(cx,cy,g){for(var i=0;i<3;i++){var d=spark('font-size:'+(18+Math.random()*16)+'px;line-height:1;');d.textContent=g;var dx=(Math.random()-.5)*90;d.animate([{transform:'translate('+cx+'px,'+cy+'px) scale(.6)',opacity:0},{transform:'translate('+(cx+dx)+'px,'+(cy-90-Math.random()*60)+'px) scale(1.2)',opacity:1,offset:.3},{transform:'translate('+(cx+dx*1.4)+'px,'+(cy-170)+'px) scale(1)',opacity:0}],{duration:1100,easing:'ease-out'}).onfinish=end(d);}}
    function stamp(cx,cy,g){var d=spark('font-size:46px;font-weight:800;color:#ff3b1d;');d.textContent=g||'✓';var base='translate('+(cx-22)+'px,'+(cy-34)+'px) rotate(-12deg) ';d.animate([{transform:base+'scale(2.6)',opacity:0},{transform:base+'scale(1)',opacity:1,offset:.25},{transform:base+'scale(1)',opacity:1,offset:.7},{transform:base+'scale(1.12)',opacity:0}],{duration:820}).onfinish=end(d);}
    function wordPop(cx,cy,w){var d=spark('font-family:var(--font-display),sans-serif;font-weight:800;font-size:30px;color:#111;-webkit-text-stroke:2px #ff3b1d;letter-spacing:-.02em;');d.textContent=w;d.animate([{transform:'translate('+cx+'px,'+(cy-20)+'px) scale(.3) rotate(-8deg)',opacity:0},{transform:'translate('+cx+'px,'+(cy-46)+'px) scale(1.2) rotate(-8deg)',opacity:1,offset:.3},{transform:'translate('+cx+'px,'+(cy-78)+'px) scale(1) rotate(-8deg)',opacity:0}],{duration:900,easing:'cubic-bezier(.2,.7,.2,1)'}).onfinish=end(d);}
    function spin(pill){pill.animate([{transform:'rotate(0) scale(1)'},{transform:'rotate(360deg) scale(1.18)',offset:.6},{transform:'rotate(360deg) scale(1)'}],{duration:620,easing:'cubic-bezier(.2,.7,.2,1)'});}
    function glitch(pill){var kf=[];for(var i=0;i<6;i++)kf.push({transform:'translate('+((Math.random()-.5)*9)+'px,'+((Math.random()-.5)*5)+'px)',filter:'hue-rotate('+(i*50)+'deg) saturate(2)'});kf.push({transform:'none',filter:'none'});pill.animate(kf,{duration:420,easing:'steps(6)'});}
    function ripple(pill){pill.animate([{backgroundColor:'#e9e7e1',color:'#111'},{backgroundColor:'#ff3b1d',color:'#fff',offset:.3},{backgroundColor:'#111',color:'#fff',offset:.6},{backgroundColor:'#e9e7e1',color:'#111'}],{duration:640,easing:'ease-in-out'});}

    // effects that spawn particles (need coords), and effects that transform the pill
    var particleFx = [
      function(p,x,y,g){confetti(x,y);},
      function(p,x,y,g){shockwave(x,y);},
      function(p,x,y,g){firework(x,y);},
      function(p,x,y,g){squares(x,y);},
      function(p,x,y,g){glyphPop(x,y,g);},
      function(p,x,y,g){stamp(x,y,g);},
      function(p,x,y,g,w){wordPop(x,y,w);}
    ];
    var pillFx = [spin, glitch, ripple];

    function pressPop(pill){ if(canAnim) pill.animate([{transform:'scale(.92)'},{transform:'scale(1)'}],{duration:180,easing:'ease-out'}); }

    function react(pill){
      var label = (pill.textContent||'').trim();
      var key = label.toLowerCase();
      var h = hash(label);
      var r = pill.getBoundingClientRect();
      var cx = r.left + r.width/2, cy = r.top + r.height/2;
      var glyph = THEME[key] || FUN[h % FUN.length];
      var word = WORDS[h % WORDS.length];
      pressPop(pill);
      if (reduce || !canAnim) { ripple(pill); return; }
      // combine a pill effect + a particle effect, chosen deterministically per skill
      pillFx[h % pillFx.length](pill);
      particleFx[(h >> 3) % particleFx.length](pill, cx, cy, glyph, word);
    }

    var pills = grid.querySelectorAll('.pill');
    for (var i = 0; i < pills.length; i++) {
      var pill = pills[i];
      pill.setAttribute('tabindex', '0');
      pill.setAttribute('role', 'button');
    }
    grid.addEventListener('click', function (e) {
      var pill = e.target.closest('.pill');
      if (pill) react(pill);
    });
    grid.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var pill = e.target.closest('.pill');
      if (pill) { e.preventDefault(); react(pill); }
    });
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
