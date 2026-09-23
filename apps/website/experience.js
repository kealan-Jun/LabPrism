/* Progressive editorial motion; no content is hidden if observers are unavailable. */
(() => {
  'use strict';
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (motion.matches || !('IntersectionObserver' in window)) return;
  const sections = [...document.querySelectorAll('[data-reveal]')];
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }, {threshold: 0.08});
  sections.forEach(section => {section.classList.add('reveal-ready'); observer.observe(section);});
  motion.addEventListener('change', event => {
    if (event.matches) { observer.disconnect(); sections.forEach(section => section.classList.add('is-visible')); }
  });
})();
