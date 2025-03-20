
// Intersection Observer for animations
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
}, {
    threshold: 0.15,
    rootMargin: '50px'
});

// Observe all experience boxes and section headings
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.experience-box, .section-heading').forEach((el) => {
        observer.observe(el);
    });
});
