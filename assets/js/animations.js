const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const menuToggle = document.querySelector(".menu-toggle");
    const siteNav = document.querySelector(".site-nav");

    if (menuToggle && siteNav) {
        menuToggle.addEventListener("click", () => {
            const isOpen = body.classList.toggle("menu-open");
            menuToggle.setAttribute("aria-expanded", String(isOpen));
        });

        siteNav.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => {
                body.classList.remove("menu-open");
                menuToggle.setAttribute("aria-expanded", "false");
            });
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth > 920) {
                body.classList.remove("menu-open");
                menuToggle.setAttribute("aria-expanded", "false");
            }
        });
    }

    const revealItems = document.querySelectorAll(".reveal");
    if (!prefersReducedMotion && "IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.14, rootMargin: "0px 0px -40px 0px" });

        revealItems.forEach((item) => observer.observe(item));
    } else {
        revealItems.forEach((item) => item.classList.add("is-visible"));
    }

    document.querySelectorAll(".media-carousel").forEach((carousel) => {
        const track = carousel.querySelector(".media-carousel__track");
        const slides = carousel.querySelectorAll(".media-frame");
        const prevButton = carousel.querySelector(".carousel-btn.prev");
        const nextButton = carousel.querySelector(".carousel-btn.next");
        const dots = carousel.querySelectorAll(".carousel-dot");

        if (!track || slides.length <= 1) {
            const controls = carousel.querySelector(".media-carousel__controls");
            if (controls) controls.hidden = true;
            return;
        }

        let current = 0;

        const update = (index) => {
            current = (index + slides.length) % slides.length;
            track.style.transform = `translateX(-${current * 100}%)`;
            dots.forEach((dot, dotIndex) => {
                dot.classList.toggle("active", dotIndex === current);
            });
        };

        prevButton?.addEventListener("click", () => update(current - 1));
        nextButton?.addEventListener("click", () => update(current + 1));
        dots.forEach((dot, index) => dot.addEventListener("click", () => update(index)));

        let startX = 0;

        carousel.addEventListener("touchstart", (event) => {
            startX = event.changedTouches[0].clientX;
        }, { passive: true });

        carousel.addEventListener("touchend", (event) => {
            const deltaX = startX - event.changedTouches[0].clientX;
            if (Math.abs(deltaX) > 35) {
                update(deltaX > 0 ? current + 1 : current - 1);
            }
        }, { passive: true });

        if (!prefersReducedMotion) {
            let intervalId = window.setInterval(() => update(current + 1), 5000);

            carousel.addEventListener("mouseenter", () => window.clearInterval(intervalId));
            carousel.addEventListener("mouseleave", () => {
                intervalId = window.setInterval(() => update(current + 1), 5000);
            });
        }
    });
});
