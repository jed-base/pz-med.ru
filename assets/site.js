(() => {
  const year = document.querySelector('[data-year]');
  if (year) year.textContent = new Date().getFullYear();

  const header = document.querySelector('[data-header]');
  const syncHeader = () => header?.classList.toggle('scrolled', window.scrollY > 12);
  syncHeader();
  window.addEventListener('scroll', syncHeader, { passive: true });

  // Публичная песочница живёт в этом же проекте на /demo/.
  // Добавляем ссылки через JS, чтобы не дублировать разметку первого экрана.
  const heroActions = document.querySelector('.hero-actions');
  if (heroActions && !heroActions.querySelector('[data-demo-link]')) {
    const currentPrimary = heroActions.querySelector('.button');
    if (currentPrimary) currentPrimary.classList.add('button-ghost');

    const demoLink = document.createElement('a');
    demoLink.className = 'button';
    demoLink.href = '/demo/';
    demoLink.target = '_blank';
    demoLink.rel = 'noopener';
    demoLink.dataset.demoLink = 'true';
    demoLink.textContent = 'Попробовать демо';
    heroActions.prepend(demoLink);
  }

  const nav = document.querySelector('.nav');
  if (nav && !nav.querySelector('[data-demo-link]')) {
    const demoNav = document.createElement('a');
    demoNav.href = '/demo/';
    demoNav.target = '_blank';
    demoNav.rel = 'noopener';
    demoNav.dataset.demoLink = 'true';
    demoNav.textContent = 'Демо';
    nav.append(demoNav);
  }

  const items = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window)) {
    items.forEach((item) => item.classList.add('visible'));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -24px 0px' });

  items.forEach((item) => observer.observe(item));
})();
