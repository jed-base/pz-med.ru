(() => {
  const year = document.querySelector('[data-year]');
  if (year) year.textContent = new Date().getFullYear();

  const header = document.querySelector('[data-header]');
  const syncHeader = () => header?.classList.toggle('scrolled', window.scrollY > 12);
  syncHeader();
  window.addEventListener('scroll', syncHeader, { passive: true });

  // На главной странице короткий блок возможностей остаётся обзором,
  // а ссылки ведут на отдельную подробную презентацию всех функций.
  document.querySelectorAll('a[href="#capabilities"]').forEach((link) => {
    link.href = '/functions/';
  });

  // Прямые ссылки на публичную демо-версию убраны.
  // Для тестирования предлагаем связаться по рабочей почте.
  const testMailHref = 'mailto:ivan@pz-med.ru?subject=%D0%A2%D0%B5%D1%81%D1%82%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5%20PZ-Med';

  document.querySelectorAll('a[href="/demo/"], a[href^="https://demo.pz-med.ru"]').forEach((link) => {
    link.href = testMailHref;
    link.removeAttribute('target');
    link.removeAttribute('rel');
    link.removeAttribute('data-demo-link');

    if (link.closest('.nav')) {
      link.textContent = 'Тестирование';
    } else if (link.classList.contains('button')) {
      link.textContent = 'Запросить тестирование';
    } else {
      link.textContent = 'Связаться для тестирования';
    }
  });

  const heroActions = document.querySelector('.hero-actions');
  if (heroActions && !heroActions.querySelector('[data-test-link]')) {
    const currentPrimary = heroActions.querySelector('.button');
    if (currentPrimary) currentPrimary.classList.add('button-ghost');

    const testLink = document.createElement('a');
    testLink.className = 'button';
    testLink.href = testMailHref;
    testLink.dataset.testLink = 'true';
    testLink.textContent = 'Запросить тестирование';
    heroActions.prepend(testLink);
  }

  const nav = document.querySelector('.nav');
  if (nav && !nav.querySelector('[data-test-link]') && !nav.querySelector('a[href^="mailto:ivan@pz-med.ru"]')) {
    const testNav = document.createElement('a');
    testNav.href = '#contact';
    testNav.dataset.testLink = 'true';
    testNav.textContent = 'Тестирование';
    nav.append(testNav);
  }

  // Контактный блок остаётся единой точкой входа для запроса тестирования.
  const contactCard = document.querySelector('#contact .contact-card');
  if (contactCard) {
    const contactText = contactCard.querySelector('p');
    if (contactText) {
      contactText.innerHTML = 'Для тестирования PZ-Med и по вопросам внедрения напишите на <a href="mailto:ivan@pz-med.ru"><strong>ivan@pz-med.ru</strong></a>.';
    }

    const contactAction = contactCard.querySelector('.button');
    if (contactAction) {
      contactAction.href = testMailHref;
      contactAction.textContent = 'Запросить тестирование';
    }
  }

  // На странице функций поясняем новый порядок доступа к тестовой версии.
  const functionsCta = document.querySelector('.functions-cta');
  if (functionsCta) {
    const eyebrow = functionsCta.querySelector('.eyebrow');
    const title = functionsCta.querySelector('h2');
    const text = functionsCta.querySelector('p');

    if (eyebrow) eyebrow.textContent = 'Тестирование PZ-Med';
    if (title) title.textContent = 'Хотите посмотреть PZ-Med в работе?';
    if (text) text.textContent = 'Доступ к тестовой версии предоставляется по запросу. Напишите на ivan@pz-med.ru, и мы направим данные для входа.';
  }

  // Мини-версия на первом экране остаётся полностью локальной HTML/CSS-моделью.
  // Внешний iframe больше не создаётся, поэтому окно отображается мгновенно.
  const productWindow = document.querySelector('.product-window');
  if (productWindow) {
    productWindow.setAttribute('aria-label', 'Мини-копия интерфейса PZ-Med с демонстрационными данными');
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