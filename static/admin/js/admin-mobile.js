/* Admin Mobile — Three-dot action menus and responsive enhancements.
   Progressive enhancement: works without JS (desktop links remain). */
(function () {
  'use strict';

  function isMobile() {
    return window.matchMedia('(max-width: 767px)').matches;
  }

  function buildThreeDotMenu(row) {
    var lastCell = row.querySelector('td:last-child');
    if (!lastCell) return null;

    var links = lastCell.querySelectorAll('a, button');
    if (links.length === 0) return null;

    var container = document.createElement('div');
    container.className = 'sboi-mobile-actions';

    var btn = document.createElement('button');
    btn.className = 'sboi-three-dot';
    btn.setAttribute('aria-label', 'Actions');
    btn.setAttribute('aria-haspopup', 'true');
    btn.textContent = '\u22EE';

    var menu = document.createElement('div');
    menu.className = 'sboi-mobile-menu';

    links.forEach(function (link) {
      var clone = link.cloneNode(true);
      clone.removeAttribute('onclick');
      menu.appendChild(clone);
    });

    container.appendChild(btn);
    container.appendChild(menu);

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var isOpen = menu.classList.contains('is-open');
      // Close all other menus
      document.querySelectorAll('.sboi-mobile-menu.is-open').forEach(function (m) {
        m.classList.remove('is-open');
      });
      if (!isOpen) {
        menu.classList.add('is-open');
      }
    });

    return container;
  }

  function enhanceChangelist() {
    if (!isMobile()) return;
    var rows = document.querySelectorAll('#result_list tbody tr');
    rows.forEach(function (row) {
      if (row.querySelector('.sboi-mobile-actions')) return;
      var menu = buildThreeDotMenu(row);
      if (menu) {
        row.appendChild(menu);
      }
    });
  }

  // Close menus on outside click
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.sboi-three-dot')) {
      document.querySelectorAll('.sboi-mobile-menu.is-open').forEach(function (m) {
        m.classList.remove('is-open');
      });
    }
  });

  // Close on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.sboi-mobile-menu.is-open').forEach(function (m) {
        m.classList.remove('is-open');
      });
    }
  });

  // Enhance on load and on resize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceChangelist);
  } else {
    enhanceChangelist();
  }

  window.addEventListener('resize', function () {
    if (isMobile()) {
      enhanceChangelist();
    } else {
      document.querySelectorAll('.sboi-mobile-actions').forEach(function (el) {
        el.remove();
      });
    }
  });
})();