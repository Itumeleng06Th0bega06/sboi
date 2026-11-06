/*
  Public / member notification bell.

  The markup is rendered server-side. This script polls the JSON feed so the
  badge stays fresh and rebuilds the list after the server changes. Opening an
  item follows its open_url, and the server marks it read before redirecting;
  there are no per-item action buttons to keep the dropdown calm.
*/
(function () {
    'use strict';

    function icon() {
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M6.2 10.3a5.8 5.8 0 0 1 8.4-5.1M17.8 12.5c0 2.2.4 3.3 1.6 3.3H4.6s1.6-1.3 1.6-5.5M10 19.2a2.2 2.2 0 0 0 4 0M3.5 3.5 20.5 20.5');
        svg.appendChild(path);
        return svg;
    }

    function row(item) {
        var link = document.createElement('a');
        link.className = 'notif-item tone-' + (item.tone || 'info');
        if (item.unread) {
            link.className += ' is-unread';
        }
        link.href = item.open_url || item.url || '#';
        link.setAttribute('data-notification-id', item.id || '');

        var title = document.createElement('span');
        title.className = 'notif-item-title';
        title.textContent = item.title || '';
        link.appendChild(title);

        if (item.body) {
            var desc = document.createElement('span');
            desc.className = 'notif-item-desc';
            desc.textContent = item.body;
            link.appendChild(desc);
        }

        var date = document.createElement('span');
        date.className = 'notif-item-date';
        date.textContent = item.date || '';
        link.appendChild(date);
        return link;
    }

    function empty() {
        var wrap = document.createElement('div');
        wrap.className = 'notif-empty';
        wrap.appendChild(icon());
        var text = document.createElement('span');
        text.textContent = "You're all caught up. No active notifications.";
        wrap.appendChild(text);
        return wrap;
    }

    function refresh(root) {
        var list = root.querySelector('[data-sboi-public-list]');
        var badge = root.querySelector('[data-sboi-public-badge]');
        if (!list || !badge) {
            return;
        }
        fetch(root.getAttribute('data-api-url'), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        }).then(function (data) {
            badge.textContent = data.badge > 99 ? '99+' : String(data.badge || 0);
            badge.hidden = !data.badge;
            list.innerHTML = '';
            if (!data.items || !data.items.length) {
                list.appendChild(empty());
                return;
            }
            data.items.forEach(function (item) {
                list.appendChild(row(item));
            });
        }).catch(function () {
            /* Keep the server-rendered list and try again on the next tick. */
        });
    }

    function closeBell(root) {
        if (!root.open) return;
        root.open = false;
        var more = root.querySelector('.notif-bell-more');
        if (more) more.open = false;
    }

    document.querySelectorAll('[data-sboi-public-bell]').forEach(function (root) {
        root.addEventListener('toggle', function () {
            if (root.open) {
                refresh(root);
            } else {
                var more = root.querySelector('.notif-bell-more');
                if (more) more.open = false;
            }
        });
        setInterval(function () { refresh(root); }, 60000);
    });

    // Close the dropdown when the page is clicked elsewhere or Escape is used.
    document.addEventListener('click', function (event) {
        document.querySelectorAll('[data-sboi-public-bell][open]').forEach(function (root) {
            if (!root.contains(event.target)) {
                closeBell(root);
            }
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('[data-sboi-public-bell][open]').forEach(closeBell);
    });

    // The account page updates read state without reloading. Ask the bell to
    // refresh its list and badge so both surfaces stay in sync.
    document.addEventListener('sboi:notifications-updated', function () {
        document.querySelectorAll('[data-sboi-public-bell]').forEach(refresh);
    });
})();
