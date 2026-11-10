/* Admin Mobile — Three-dot action menus and responsive enhancements.
   Progressive enhancement: works without JS (desktop links remain). */
(function () {
  'use strict';

  function isMobile() {
    return window.matchMedia('(max-width: 767px)').matches;
  }

  function buildThreeDotMenu(row) {
    // Search ALL cells for action links, not just last child (devotion rows
    // have action-relevant content in various columns)
    var cells = row.querySelectorAll('td, th');
    var links = [];
    cells.forEach(function (cell) {
      if (cell.classList.contains('action-checkbox')) return;
      cell.querySelectorAll('a, button').forEach(function (link) {
        // Skip edit links that are in the first column (used for row click)
        if (!cell.closest('th') && links.length >= 0) {
          links.push(link);
        }
      });
    });
    if (links.length === 0) return null;

    // Find the primary edit/change link to use for row click
    var changeLink = row.querySelector('td a[href], th a[href]');
    var changeHref = changeLink ? changeLink.href : null;

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
    container.dataset.changeHref = changeHref || '';

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

  function makeRowClickable(row) {
    // Make entire row clickable to the edit page, except when clicking links/buttons/checkboxes
    var changeLink = row.querySelector('th a[href], td a[href]');
    if (!changeLink) return;
    var changeHref = changeLink.href;

    row.addEventListener('click', function (e) {
      // Ignore clicks on links, buttons, inputs, or the three-dot menu
      if (e.target.closest('a, button, input, select, textarea, .sboi-mobile-actions, .sboi-three-dot, .sboi-mobile-menu')) {
        return;
      }
      window.location.href = changeHref;
    });
    row.style.cursor = 'pointer';
    row.style.position = 'relative';
  }

  function enhanceChangelist() {
    var rows = document.querySelectorAll('#result_list tbody tr');
    rows.forEach(function (row) {
      makeRowClickable(row);
      if (!isMobile()) return;
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