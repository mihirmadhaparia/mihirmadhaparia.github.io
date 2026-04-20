/* ─── Orb background animation ────────────────────────────────── */
(function () {
    const canvas = document.getElementById("bg-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    // Each orb: baseX/Y as fraction of viewport, radius fraction, color, phase offsets
    const orbs = [
        { bx: 0.12, by: 0.18, r: 0.42, color: "rgba(0,113,227,0.09)",  sx: 0.62, sy: 0.48, ph: 0.0 },
        { bx: 0.80, by: 0.12, r: 0.36, color: "rgba(94,92,230,0.07)",   sx: 0.45, sy: 0.72, ph: 2.1 },
        { bx: 0.55, by: 0.72, r: 0.48, color: "rgba(52,199,89,0.055)",  sx: 0.58, sy: 0.38, ph: 4.2 },
        { bx: 0.88, by: 0.78, r: 0.32, color: "rgba(0,199,190,0.065)",  sx: 0.80, sy: 0.60, ph: 1.5 },
    ];

    function resize() {
        canvas.width  = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const t = Date.now() * 0.00016; // very slow drift

        orbs.forEach(function (orb) {
            const x = (orb.bx + Math.sin(t * orb.sx + orb.ph) * 0.10) * canvas.width;
            const y = (orb.by + Math.cos(t * orb.sy + orb.ph) * 0.09) * canvas.height;
            const r = orb.r * Math.min(canvas.width, canvas.height);

            const g = ctx.createRadialGradient(x, y, 0, x, y, r);
            g.addColorStop(0, orb.color);
            g.addColorStop(1, "rgba(0,0,0,0)");

            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
        });

        requestAnimationFrame(draw);
    }

    resize();
    window.addEventListener("resize", resize, { passive: true });

    // Respect reduced motion — still render static orbs, just don't animate
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        draw(); // draw once, stop
    } else {
        draw();
    }
})();

/* ─── Everything else ─────────────────────────────────────────── */
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

document.addEventListener("DOMContentLoaded", function () {

    /* ── Mobile menu ── */
    var body        = document.body;
    var menuToggle  = document.querySelector(".menu-toggle");
    var siteNav     = document.querySelector(".site-nav");

    if (menuToggle && siteNav) {
        menuToggle.addEventListener("click", function () {
            var isOpen = body.classList.toggle("menu-open");
            menuToggle.setAttribute("aria-expanded", String(isOpen));
        });

        siteNav.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                body.classList.remove("menu-open");
                menuToggle.setAttribute("aria-expanded", "false");
            });
        });

        window.addEventListener("resize", function () {
            if (window.innerWidth > 900) {
                body.classList.remove("menu-open");
                menuToggle.setAttribute("aria-expanded", "false");
            }
        });
    }

    /* ── Scroll reveal ── */
    var revealItems = document.querySelectorAll(".reveal");
    if (!prefersReducedMotion && "IntersectionObserver" in window) {
        var revealObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });

        revealItems.forEach(function (item) { revealObserver.observe(item); });
    } else {
        revealItems.forEach(function (item) { item.classList.add("is-visible"); });
    }

    /* ── Media carousels ── */
    document.querySelectorAll(".media-carousel").forEach(function (carousel) {
        var track   = carousel.querySelector(".media-carousel__track");
        var slides  = carousel.querySelectorAll(".media-frame");
        var prev    = carousel.querySelector(".carousel-btn.prev");
        var next    = carousel.querySelector(".carousel-btn.next");
        var dots    = carousel.querySelectorAll(".carousel-dot");

        if (!track || slides.length <= 1) {
            var controls = carousel.querySelector(".media-carousel__controls");
            if (controls) controls.hidden = true;
            return;
        }

        var current = 0;

        function update(index) {
            current = (index + slides.length) % slides.length;
            track.style.transform = "translateX(-" + (current * 100) + "%)";
            dots.forEach(function (dot, i) {
                dot.classList.toggle("active", i === current);
            });
        }

        if (prev) prev.addEventListener("click", function () { update(current - 1); });
        if (next) next.addEventListener("click", function () { update(current + 1); });
        dots.forEach(function (dot, i) {
            dot.addEventListener("click", function () { update(i); });
        });

        // Touch swipe
        var startX = 0;
        carousel.addEventListener("touchstart", function (e) {
            startX = e.changedTouches[0].clientX;
        }, { passive: true });
        carousel.addEventListener("touchend", function (e) {
            var dx = startX - e.changedTouches[0].clientX;
            if (Math.abs(dx) > 34) update(dx > 0 ? current + 1 : current - 1);
        }, { passive: true });

        // Auto-advance
        if (!prefersReducedMotion) {
            var timer = window.setInterval(function () { update(current + 1); }, 5000);
            carousel.addEventListener("mouseenter", function () { clearInterval(timer); });
            carousel.addEventListener("mouseleave", function () {
                timer = window.setInterval(function () { update(current + 1); }, 5000);
            });
        }
    });
});
