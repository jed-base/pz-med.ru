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

  // Первый экран показывает не нарисованный макет, а настоящее демо PZ-Med.
  // Интерфейс работает в отдельном preview-режиме: он уменьшен до размеров
  // карточки, подсвечивает элементы при наведении и переводит в полное демо
  // при любом клике.
  const mockLayout = document.querySelector('.mock-layout');
  if (mockLayout && !mockLayout.querySelector('[data-live-preview]')) {
    if (!document.getElementById('pz-live-preview-style')) {
      const style = document.createElement('style');
      style.id = 'pz-live-preview-style';
      style.textContent = `
        .mock-layout.pz-live-preview-shell {
          display: block;
          position: relative;
          min-height: 480px;
          overflow: hidden;
          background: #eef4f1;
        }
        .pz-live-preview {
          position: absolute;
          inset: 0;
          overflow: hidden;
          background: #eef4f1;
          isolation: isolate;
        }
        .pz-live-preview__iframe {
          position: absolute;
          top: 0;
          left: 0;
          display: block;
          border: 0;
          margin: 0;
          transform-origin: 0 0;
          background: #f6f8f7;
        }
        .pz-live-preview__hint {
          position: absolute;
          right: 14px;
          bottom: 14px;
          z-index: 3;
          max-width: calc(100% - 28px);
          padding: 9px 12px;
          border: 1px solid rgba(13, 92, 70, .14);
          border-radius: 11px;
          background: rgba(255, 255, 255, .94);
          box-shadow: 0 10px 30px rgba(16, 35, 28, .12);
          color: #0d5c46;
          font-size: .72rem;
          font-weight: 800;
          line-height: 1.25;
          opacity: 0;
          transform: translateY(5px);
          transition: opacity .18s ease, transform .18s ease;
          pointer-events: none;
        }
        .pz-live-preview:hover .pz-live-preview__hint {
          opacity: 1;
          transform: translateY(0);
        }
        @media (max-width: 760px) {
          .mock-layout.pz-live-preview-shell { min-height: 390px; }
          .pz-live-preview__hint { display: none; }
        }
      `;
      document.head.append(style);
    }

    mockLayout.classList.add('pz-live-preview-shell');
    mockLayout.innerHTML = `
      <div class="pz-live-preview" data-live-preview>
        <iframe
          class="pz-live-preview__iframe"
          data-live-preview-frame
          src="https://demo.pz-med.ru/?preview=1"
          title="Интерактивная мини-версия PZ-Med"
          loading="eager"
          referrerpolicy="strict-origin-when-cross-origin"
        ></iframe>
        <div class="pz-live-preview__hint" aria-hidden="true">
          Нажмите на элемент — откроется демо
        </div>
      </div>
    `;

    const preview = mockLayout.querySelector('[data-live-preview]');
    const iframe = mockLayout.querySelector('[data-live-preview-frame]');
    const virtualWidth = 1366;

    const resizePreview = () => {
      if (!preview || !iframe || !preview.clientWidth || !preview.clientHeight) return;
      const scale = preview.clientWidth / virtualWidth;
      iframe.style.width = `${virtualWidth}px`;
      iframe.style.height = `${Math.ceil(preview.clientHeight / scale)}px`;
      iframe.style.transform = `scale(${scale})`;
    };

    resizePreview();

    if ('ResizeObserver' in window) {
      const previewObserver = new ResizeObserver(resizePreview);
      previewObserver.observe(preview);
    } else {
      window.addEventListener('resize', resizePreview, { passive: true });
    }
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