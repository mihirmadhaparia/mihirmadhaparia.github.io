
// Intersection Observer for animations
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
        }
    });
}, {
    threshold: 0.1
});

// Observe all experience boxes and section headings
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.experience-box, .section-heading').forEach((el) => {
        observer.observe(el);
    });
});
