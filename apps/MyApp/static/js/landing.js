(function () {
  const nav = document.getElementById('landing-nav');
  const menuButton = document.querySelector('.menu-toggle');
  const mobileMenu = document.getElementById('mobile-menu');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const updateNav = () => nav && nav.classList.toggle('scrolled', window.scrollY > 24);
  updateNav();
  window.addEventListener('scroll', updateNav, { passive: true });

  if (menuButton && mobileMenu) {
    menuButton.addEventListener('click', () => {
      const open = mobileMenu.classList.toggle('open');
      menuButton.setAttribute('aria-expanded', String(open));
    });
    mobileMenu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      mobileMenu.classList.remove('open');
      menuButton.setAttribute('aria-expanded', 'false');
    }));
  }

  const reveal = document.querySelectorAll('.reveal');
  if (reduceMotion || !('IntersectionObserver' in window)) reveal.forEach((item) => item.classList.add('visible'));
  else {
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); }
    }), { threshold: 0.14 });
    reveal.forEach((item) => observer.observe(item));
  }

  const stage = document.querySelector('.hero-stage');
  const sculpture = document.querySelector('[data-tilt]');
  if (stage && sculpture && !reduceMotion) {
    stage.addEventListener('pointermove', (event) => {
      const rect = stage.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      sculpture.style.transform = `rotateX(${y * -5}deg) rotateY(${x * 7}deg)`;
    }, { passive: true });
    stage.addEventListener('pointerleave', () => { sculpture.style.transform = ''; });
  }

  // Camera-like depth movement while the hero leaves the viewport. It is
  // deliberately capped so the navigation and CTA remain easy to use.
  if (stage && !reduceMotion) {
    let ticking = false;
    const moveScene = () => {
      const progress = Math.max(-0.35, Math.min(1, window.scrollY / Math.max(stage.offsetHeight, 1)));
      stage.style.transform = `translate3d(0, ${progress * -42}px, 0) scale(${1 - progress * .035})`;
      ticking = false;
    };
    window.addEventListener('scroll', () => {
      if (!ticking) { window.requestAnimationFrame(moveScene); ticking = true; }
    }, { passive: true });
  }
})();
