(function () {
  'use strict';

  /* ---------- Mobile bottom nav: About bottom sheet ---------- */
  var aboutBtn = document.getElementById('bottomAboutBtn');
  var navSheet = document.getElementById('navSheet');
  if (aboutBtn && navSheet) {
    var sheetTimer = null;
    function closeSheet() {
      navSheet.classList.remove('open');
      aboutBtn.setAttribute('aria-expanded', 'false');
      document.body.classList.remove('sheet-open');
      if (sheetTimer) window.clearTimeout(sheetTimer);
      sheetTimer = window.setTimeout(function () { navSheet.hidden = true; sheetTimer = null; }, 300);
    }
    function openSheet() {
      if (sheetTimer) { window.clearTimeout(sheetTimer); sheetTimer = null; }
      navSheet.hidden = false;
      window.requestAnimationFrame(function () { navSheet.classList.add('open'); });
      aboutBtn.setAttribute('aria-expanded', 'true');
      document.body.classList.add('sheet-open');
    }
    aboutBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (navSheet.hidden) { openSheet(); } else { closeSheet(); }
    });
    navSheet.addEventListener('click', function (e) {
      if (e.target.closest('[data-sheet-close]') || e.target.closest('a')) closeSheet();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !navSheet.hidden) closeSheet();
    });
  }

  /* Header shadow on scroll */
  var header = document.getElementById('siteHeader');
  if (header) {
    window.addEventListener('scroll', function () {
      header.classList.toggle('scrolled', window.scrollY > 10);
    });
  }

  /* ---------- Sliders ---------- */
  function initSlider(rootId, trackId, prevId, nextId, dotsId) {
    var root = document.getElementById(rootId);
    if (!root) return;
    var track = document.getElementById(trackId);
    var slides = track ? track.children : [];
    var dotsWrap = document.getElementById(dotsId);
    var dots = dotsWrap ? dotsWrap.children : [];
    if (!slides.length) return;

    var index = 0;
    var timer = null;
    var stripTitle = document.getElementById('heroStripTitle');
    var stripCaption = document.getElementById('heroStripCaption');

    function goTo(i) {
      index = (i + slides.length) % slides.length;
      for (var s = 0; s < slides.length; s++) slides[s].classList.toggle('active', s === index);
      for (var d = 0; d < dots.length; d++) dots[d].classList.toggle('active', d === index);
      if (stripTitle && slides[index].getAttribute('data-title')) {
        stripTitle.textContent = slides[index].getAttribute('data-title');
      }
      if (stripCaption && slides[index].getAttribute('data-caption')) {
        stripCaption.textContent = slides[index].getAttribute('data-caption');
      }
    }

    function next() { goTo(index + 1); }
    function prev() { goTo(index - 1); }

    function start() {
      if (slides.length < 2) return;
      stop();
      timer = setInterval(next, 5500);
    }
    function stop() { if (timer) clearInterval(timer); timer = null; }

    var prevBtn = document.getElementById(prevId);
    var nextBtn = document.getElementById(nextId);
    if (prevBtn) prevBtn.addEventListener('click', function () { stop(); prev(); start(); });
    if (nextBtn) nextBtn.addEventListener('click', function () { stop(); next(); start(); });

    if (dots.length) {
      Array.prototype.forEach.call(dots, function (dot, i) {
        dot.addEventListener('click', function () { stop(); goTo(i); start(); });
      });
    }

    root.addEventListener('mouseenter', stop);
    root.addEventListener('mouseleave', start);
    start();
  }

  initSlider('heroSlider', 'heroTrack', 'heroPrev', 'heroNext', 'heroDots');
  initSlider('gallerySlider', 'galleryTrack', 'galleryPrev', 'galleryNext', 'galleryDots');

  /* ---------- Blackboard pill sections ---------- */
  var pillButtons = document.querySelectorAll('[data-pill]');
  var pillPanels = document.querySelectorAll('[data-tabpanel]');

  function openPill(name) {
    pillButtons.forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-pill') === name);
      btn.setAttribute('aria-selected', btn.getAttribute('data-pill') === name ? 'true' : 'false');
    });
    pillPanels.forEach(function (p) {
      p.classList.toggle('hidden', p.getAttribute('data-tabpanel') !== name);
    });
  }

  pillButtons.forEach(function (btn) {
    btn.addEventListener('click', function () { openPill(btn.getAttribute('data-pill')); });
  });

  /* Quick-link sub-pills in nav sync with page pills */
  var navSubtabLinks = document.querySelectorAll('[data-tablink]');
  navSubtabLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      var name = link.getAttribute('data-tablink');
      if (openPill) openPill(name);
    });
  });

  /* ---------- RSVP modal ---------- */
  var modal = document.getElementById('rsvpModal');
  var form = document.getElementById('rsvpForm');
  var eventName = document.getElementById('rsvpEventName');
  var rsvpButtons = document.querySelectorAll('[data-rsvp]');
  var closeBtn = document.getElementById('rsvpClose');

  rsvpButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-rsvp');
      var title = btn.getAttribute('data-rsvp-title');
      var field = form ? form.querySelector('[name="event"]') : null;
      if (field) field.value = id;
      if (eventName) eventName.textContent = title || '';
      if (modal) modal.classList.add('open');
    });
  });
  if (closeBtn) closeBtn.addEventListener('click', function () { modal.classList.remove('open'); });
  if (modal) {
    modal.addEventListener('click', function (e) { if (e.target === modal) modal.classList.remove('open'); });
  }

  /* ---------- Lightbox ---------- */
  var lightbox = document.getElementById('lightbox');
  var lightboxImg = document.getElementById('lightboxImg');
  var lightboxCaption = document.getElementById('lightboxCaption');
  var lightboxClose = document.getElementById('lightboxClose');

  function openLightbox(img) {
    if (!lightbox || !lightboxImg) return;
    lightboxImg.src = img.getAttribute('data-full') || img.src;
    lightboxImg.alt = img.alt || '';
    lightboxCaption.textContent = img.alt || '';
    lightbox.classList.add('open');
    lightbox.setAttribute('aria-hidden', 'false');
  }

  document.addEventListener('click', function (e) {
    var target = e.target.closest('[data-lightbox]');
    if (target) {
      e.preventDefault();
      openLightbox(target);
    }
  });

  if (lightboxClose) {
    lightboxClose.addEventListener('click', function () {
      lightbox.classList.remove('open');
      lightbox.setAttribute('aria-hidden', 'true');
    });
  }
  if (lightbox) {
    lightbox.addEventListener('click', function (e) {
      if (e.target === lightbox) {
        lightbox.classList.remove('open');
        lightbox.setAttribute('aria-hidden', 'true');
      }
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && lightbox && lightbox.classList.contains('open')) {
      lightbox.classList.remove('open');
      lightbox.setAttribute('aria-hidden', 'true');
    }
  });

  /* ---------- Share row expander (devotion cards) ----------
     The platform buttons stay in the DOM but are hidden until the Share
     trigger is pressed. Toggling is class-based so the delegated share
     handler above keeps working unchanged once the buttons are visible. */
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-share-toggle]');
    if (!trigger) return;
    var row = trigger.closest('.share-row');
    if (!row) return;
    var open = row.classList.toggle('is-open');
    trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  /* ---------- Share buttons ---------- */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-share]');
    if (!btn) return;
    var row = btn.closest('.share-row');
    var title = row ? row.getAttribute('data-share-title') || '' : '';
    var url = row ? row.getAttribute('data-share-url') || window.location.href : window.location.href;
    var full = window.location.origin + url;
    var text = title + ' | Shekinah Blaze Outreach International';
    var shareUrl = full;

    switch (btn.getAttribute('data-share')) {
      case 'whatsapp':
        shareUrl = 'https://wa.me/?text=' + encodeURIComponent(text + ' ' + full);
        break;
      case 'facebook':
        shareUrl = 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(full);
        break;
      case 'x':
        shareUrl = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(text) + '&url=' + encodeURIComponent(full);
        break;
      case 'copy':
        if (navigator.clipboard) {
          var original = btn.innerHTML;
          navigator.clipboard.writeText(full).then(function () {
            btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41Z"/></svg>';
            btn.classList.add('copied');
            setTimeout(function () { btn.innerHTML = original; btn.classList.remove('copied'); }, 1500);
          });
        }
        return;
    }
    window.open(shareUrl, '_blank', 'noopener,width=600,height=500');
  });

  /* ---------- Nav dropdown (About chapters) ---------- */
  var navDropdown = document.getElementById('navAboutDropdown');
  if (navDropdown) {
    var navToggle = document.getElementById('navAboutToggle');
    var navMenu = navDropdown.querySelector('.nav-dropdown-menu');
    function closeNavDropdown() {
      navDropdown.classList.remove('open');
      if (navToggle) navToggle.setAttribute('aria-expanded', 'false');
    }
    if (navToggle) {
      navToggle.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var open = navDropdown.classList.toggle('open');
        navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }
    if (navMenu) {
      navMenu.addEventListener('click', function (e) {
        if (e.target.closest('a')) {
          closeNavDropdown();
        }
      });
    }
    document.addEventListener('click', function (e) {
      if (!e.target.closest('#navAboutDropdown')) closeNavDropdown();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeNavDropdown();
    });
  }

  /* ---------- Back to top ---------- */
  var toTop = document.getElementById('toTop');
  if (toTop) {
    function updateToTop() {
      toTop.classList.toggle('show', window.scrollY > 150);
    }
    window.addEventListener('scroll', updateToTop, { passive: true });
    updateToTop();
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ---------- Reveal on scroll ---------- */
  var revealEls = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add('visible'); });
  }

  /* ---------- Church membership: family details ----------
     A spouse only applies to married members. The field stays in the DOM so
     a non-JS submission still works; the server clears a spouse name when the
     marital status is not "married". */
  var maritalInputs = document.querySelectorAll('input[name="marital_status"]');
  var spouseInput = document.querySelector('.church-form input[name="spouse_name"]');
  if (maritalInputs.length && spouseInput) {
    var spouseField = spouseInput.closest('.form-field');
    var syncSpouseField = function () {
      var checked = document.querySelector('input[name="marital_status"]:checked');
      var married = !!checked && checked.value === 'married';
      if (spouseField) spouseField.hidden = !married;
      if (!married) spouseInput.value = '';
    };
    maritalInputs.forEach(function (input) {
      input.addEventListener('change', syncSpouseField);
    });
    syncSpouseField();
  }

  /* ---------- Date inputs ----------
     Date fields render as text boxes so they can show a placeholder.
     They switch to a native date picker on focus, and back to text when
     left empty, which keeps the form clean without losing the calendar. */
  document.querySelectorAll('input[data-date]').forEach(function (el) {
    el.addEventListener('focus', function () { el.type = 'date'; });
    el.addEventListener('blur', function () {
      if (!el.value) el.type = 'text';
    });
  });
})();

