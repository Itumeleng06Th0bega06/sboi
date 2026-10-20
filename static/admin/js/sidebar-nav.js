/*
  Admin shell behaviours.

  The admin no longer performs in-place (SPA) navigation: Django's own admin
  scripts rely on a real page load, and the old navigation shim also tried to
  initialise third-party JS widgets that no longer exist. What remains here are
  the small, dependency-free niceties for the custom header:

    - only one header dropdown can be open at a time;
    - clicking outside or pressing Escape closes them;
    - a `sboi:admin-loaded` event is dispatched once the page is ready.

  The event is kept for other admin scripts (row actions, notification bell)
  so they have a single, predictable hook.
*/
(function () {
    'use strict';

    var MENUS = '.sboi-menu';

    function closeMenu(menu) {
        if (menu && menu.open) {
            menu.open = false;
        }
    }

    function closeAll(except) {
        document.querySelectorAll(MENUS + '[open]').forEach(function (menu) {
            if (menu !== except) {
                closeMenu(menu);
            }
        });
    }

    function wireMenus() {
        document.querySelectorAll(MENUS).forEach(function (menu) {
            menu.addEventListener('toggle', function () {
                if (menu.open) {
                    closeAll(menu);
                }
            });
        });

        document.addEventListener('click', function (event) {
            if (!event.target.closest || !event.target.closest(MENUS)) {
                closeAll(null);
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }
            var open = document.querySelector(MENUS + '[open]');
            if (!open) {
                return;
            }
            closeMenu(open);
            var summary = open.querySelector('summary');
            if (summary) {
                summary.focus();
            }
        });

        /* A menu link navigates away; close the panel immediately so it does
           not linger if the browser restores the page from bfcache. */
        document.querySelectorAll(MENUS + ' a, ' + MENUS + ' button[type="submit"]').forEach(function (item) {
            item.addEventListener('click', function () {
                closeAll(null);
            });
        });
    }

    function ready(fn) {
        /* Deferred scripts execute at readyState "interactive", just before
           DOMContentLoaded. Queue the work so we run after Django's own
           deferred admin scripts rather than before them. */
        if (document.readyState === 'complete') {
            fn();
        } else {
            document.addEventListener('DOMContentLoaded', fn, { once: true });
        }
    }

    ready(function () {
        wireMenus();
        document.dispatchEvent(new CustomEvent('sboi:admin-loaded'));
    });
})();
