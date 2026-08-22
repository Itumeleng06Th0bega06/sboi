(function () {
    'use strict';

    var PREFIX = '/' + (window.location.pathname.split('/')[1] || 'admin');
    var API_URL = window.location.origin + PREFIX + '/notifications/';
    var DASHBOARD_URL = window.location.origin + PREFIX + '/';
    var REFRESH_MS = 60000;

    var badgeEl;
    var listEl;

    function el(tag, className) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        return node;
    }

    function row(item) {
        var a = el('a', 'sboi-bell-item tone-' + item.tone);
        a.href = item.url;

        var icon = el('span', 'sboi-bell-icon');
        icon.innerHTML = '<i class="' + item.icon + '" aria-hidden="true"></i>';

        var label = el('span', 'sboi-bell-label');
        label.textContent = item.label;

        var count = el('span', 'sboi-bell-count' + (item.count === 0 ? ' zero' : ''));
        count.textContent = String(item.count);

        a.appendChild(icon);
        a.appendChild(label);
        a.appendChild(count);
        return a;
    }

    function render(data) {
        if (!badgeEl || !listEl) {
            return;
        }
        if (data.badge > 0) {
            badgeEl.textContent = data.badge > 99 ? '99+' : String(data.badge);
            badgeEl.hidden = false;
        } else {
            badgeEl.hidden = true;
        }
        listEl.innerHTML = '';
        if (!data.items.length) {
            var empty = el('div', 'sboi-bell-empty');
            empty.innerHTML = '<i class="fa-regular fa-bell-slash" aria-hidden="true"></i><br>You&rsquo;re all caught up.';
            listEl.appendChild(empty);
            return;
        }
        data.items.forEach(function (item) {
            listEl.appendChild(row(item));
        });
    }

    function refresh() {
        fetch(API_URL, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.json();
        }).then(render).catch(function () {
            /* Leave whatever is rendered; try again on the next tick. */
        });
    }

    function inject() {
        var nav = document.querySelector('#jazzy-navbar .navbar-nav.ms-auto');
        if (!nav || document.getElementById('sboi-bell-item')) {
            return;
        }

        var li = el('li', 'nav-item dropdown');
        li.id = 'sboi-bell-item';

        var toggle = el('a', 'nav-link btn sboi-bell-toggle');
        toggle.id = 'sboi-bell-toggle';
        toggle.href = '#';
        toggle.setAttribute('role', 'button');
        toggle.setAttribute('data-bs-toggle', 'dropdown');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.title = 'Notifications';
        toggle.innerHTML = '<i class="fa-regular fa-bell" aria-hidden="true"></i>';

        badgeEl = el('span', 'sboi-bell-badge');
        badgeEl.hidden = true;
        toggle.appendChild(badgeEl);

        var menu = el('div', 'dropdown-menu dropdown-menu-end sboi-bell-menu');
        menu.setAttribute('aria-labelledby', 'sboi-bell-toggle');

        var head = el('div', 'sboi-bell-head');
        head.textContent = 'Notifications';
        menu.appendChild(head);

        listEl = el('div', 'sboi-bell-list');
        menu.appendChild(listEl);

        var foot = el('a', 'sboi-bell-foot');
        foot.href = DASHBOARD_URL;
        foot.innerHTML = '<i class="fa-solid fa-gauge-high" aria-hidden="true"></i> Open dashboard';
        menu.appendChild(foot);

        li.appendChild(toggle);
        li.appendChild(menu);

        var userLi = document.getElementById('jazzy-usermenu');
        var anchor = userLi ? (userLi.closest('li') || userLi) : null;
        if (anchor && nav.contains(anchor)) {
            nav.insertBefore(li, anchor);
        } else {
            nav.appendChild(li);
        }

        toggle.addEventListener('show.bs.dropdown', refresh);
    }

    inject();
    refresh();
    setInterval(refresh, REFRESH_MS);
    document.addEventListener('sboi:admin-loaded', refresh);
})();
