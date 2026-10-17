/* Single "Add" dropdown in the admin navbar, replacing the row of
 * quick-action buttons that used to sit on the dashboard.
 * The action list is rendered server-side as JSON by base_site.html. */
(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') {
            fn();
        } else {
            document.addEventListener('DOMContentLoaded', fn);
        }
    }

    ready(function () {
        var dataEl = document.getElementById('sboi-quick-actions-data');
        if (!dataEl || document.getElementById('sboi-quickadd')) {
            return;
        }

        var actions;
        try {
            actions = JSON.parse(dataEl.textContent);
        } catch (e) {
            return;
        }
        if (!actions || !actions.length) {
            return;
        }

        var nav = document.querySelector('#jazzy-navbar .navbar-nav.ms-auto');
        if (!nav) {
            return;
        }

        var li = document.createElement('li');
        li.className = 'nav-item dropdown sboi-quickadd';
        li.id = 'sboi-quickadd';

        var toggle = document.createElement('a');
        toggle.className = 'nav-link btn sboi-quickadd-toggle';
        toggle.href = '#';
        toggle.setAttribute('role', 'button');
        toggle.setAttribute('data-bs-toggle', 'dropdown');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('title', 'Add content');
        toggle.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i>' +
            '<span class="sboi-quickadd-text">Add</span>';

        var menu = document.createElement('div');
        menu.className = 'dropdown-menu dropdown-menu-end sboi-quickadd-menu';

        actions.forEach(function (action) {
            var item = document.createElement('a');
            item.className = 'dropdown-item sboi-quickadd-item';
            item.href = action.url;
            item.innerHTML = '<i class="' + action.icon + '" aria-hidden="true"></i>' +
                '<span>' + action.label + '</span>';
            menu.appendChild(item);
        });

        li.appendChild(toggle);
        li.appendChild(menu);
        nav.insertBefore(li, nav.firstChild);
    });
})();
