// ─── Scroll-triggered animations ─────────────────────────────
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    entry.target.classList.add('visible');
                });
            });
        }
    });
}, { threshold: 0.10, rootMargin: '40px' });

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.experience-box, .section-heading').forEach(el => {
        observer.observe(el);
    });

    // ─── Navbar shrink on scroll ──────────────────────────────
    let lastScrollTop = 0;
    const navbar = document.querySelector('nav');
    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        if (scrollTop > lastScrollTop && scrollTop > 60) {
            navbar.classList.add('shrink');
        } else {
            navbar.classList.remove('shrink');
        }
        lastScrollTop = Math.max(scrollTop, 0);
    }, { passive: true });

    // ─── Image Carousels ──────────────────────────────────────
    document.querySelectorAll('.card-image-panel').forEach(panel => {
        const count = parseInt(panel.dataset.count || '0', 10);

        // Hide panels with no images
        if (count === 0) {
            panel.style.display = 'none';
            return;
        }

        // No controls needed for single image
        if (count === 1) {
            const controls = panel.querySelector('.carousel-controls');
            if (controls) controls.style.display = 'none';
            return;
        }

        const track  = panel.querySelector('.carousel-track');
        const dots   = panel.querySelectorAll('.carousel-dot');
        const prevBtn = panel.querySelector('.carousel-btn.prev');
        const nextBtn = panel.querySelector('.carousel-btn.next');

        if (!track) return;

        let current = 0;

        function goTo(index) {
            current = (index + count) % count;
            track.style.transform = `translateX(-${current * 100}%)`;
            dots.forEach((d, i) => d.classList.toggle('active', i === current));
        }

        if (prevBtn) prevBtn.addEventListener('click', () => goTo(current - 1));
        if (nextBtn) nextBtn.addEventListener('click', () => goTo(current + 1));
        dots.forEach((dot, i) => dot.addEventListener('click', () => goTo(i)));

        // Touch / swipe support
        let touchStartX = 0;
        panel.addEventListener('touchstart', e => {
            touchStartX = e.changedTouches[0].clientX;
        }, { passive: true });
        panel.addEventListener('touchend', e => {
            const diff = touchStartX - e.changedTouches[0].clientX;
            if (Math.abs(diff) > 40) goTo(diff > 0 ? current + 1 : current - 1);
        }, { passive: true });

        // Auto-advance every 4s (pause on hover)
        let autoTimer = setInterval(() => goTo(current + 1), 4000);
        panel.addEventListener('mouseenter', () => clearInterval(autoTimer));
        panel.addEventListener('mouseleave', () => {
            autoTimer = setInterval(() => goTo(current + 1), 4000);
        });
    });
});
