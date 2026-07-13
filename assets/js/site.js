/* ============================================================
   MIHIR MADHAPARIA — site behavior (vanilla, no build step)
   ============================================================ */
(function () {
  'use strict';

  var TYPEFACES = {
    archivo: "'Archivo', sans-serif",
    anton:   "'Anton', sans-serif",
    syne:    "'Syne', sans-serif",
    space:   "'Space Grotesk', sans-serif"
  };
  var KEY = 'mm-typeface';
  var DEFAULT = 'space';

  function savedTypeface() {
    try { return localStorage.getItem(KEY) || DEFAULT; } catch (e) { return DEFAULT; }
  }
  function applyTypeface(name) {
    var stack = TYPEFACES[name] || TYPEFACES[DEFAULT];
    document.documentElement.style.setProperty('--font-display', stack);
    try { localStorage.setItem(KEY, name); } catch (e) {}
    paintFontButtons(name);
  }
  function paintFontButtons(active) {
    var bar = document.querySelector('.fontbar__btns');
    if (!bar) return;
    var btns = bar.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('is-active', btns[i].getAttribute('data-font') === active);
    }
  }
  function initFontSwitcher() {
    applyTypeface(savedTypeface());
    var bar = document.querySelector('.fontbar__btns');
    if (!bar) return;
    bar.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-font]');
      if (btn) applyTypeface(btn.getAttribute('data-font'));
    });
  }

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

  function init() {
    initFontSwitcher();
    initNav();
    initReveal();
    initCursorTrail();
    initFlow();
    initCounts();
    initWeekChart();
    initPhotoCaps();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
