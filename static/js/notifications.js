/*
  Public / member notification bell.

  The markup is rendered server-side. This script polls the JSON feed so the
  badge stays fresh and lets a visitor or member mark an item read or dismiss
  it without reloading the page. All state changes are posted to the same
  notification service used by the admin bell.
*/
(function () {
    'use strict';

    function csrfToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function act(url) {
        if (!url) {
            return Promise.resolve();
        }
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken()
            }
        });
    }

    function bind(root) {
        root.querySelectorAll('[data-notif-action]').forEach(function (button) {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                button.disabled = true;
                act(button.getAttribute('data-notif-action'))
                    .then(function () { refresh(root); })
                    .catch(function () { button.disabled = false; });
            });
        });
    }

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
        var wrap = document.createElement('div');
        wrap.className = 'notif-item tone-' + (item.tone || 'info');

        var link = document.createElement('a');
        link.className = 'notif-item-link';
        link.href = item.url || '#';

        var title = document.createElement('span');
        title.className = 'notif-item-title';
        title.textContent = item.title || '';

        var desc = document.createElement('span');
        desc.className = 'notif-item-desc';
        desc.textContent = item.body || '';

        var date = document.createElement('span');
        date.className = 'notif-item-date';
        date.textContent = item.date || '';

        link.appendChild(title);
        if (item.body) {
            link.appendChild(desc);
        }
        link.appendChild(date);
        wrap.appendChild(link);

        var actions = document.createElement('div');
        actions.className = 'notif-item-actions';
        if (item.unread) {
            var read = document.createElement('button');
            read.type = 'button';
            read.className = 'notif-item-action';
            read.setAttribute('data-notif-action', item.mark_read_url || '');
            read.textContent = 'Mark read';
            actions.appendChild(read);
        }
        var dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'notif-item-action';
        dismiss.setAttribute('data-notif-action', item.dismiss_url || '');
        dismiss.textContent = 'Dismiss';
        actions.appendChild(dismiss);
        wrap.appendChild(actions);
        return wrap;
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
            bind(list);
        }).catch(function () {
            /* Keep the server-rendered list and try again on the next tick. */
        });
    }

    document.querySelectorAll('[data-sboi-public-bell]').forEach(function (root) {
        bind(root);
        root.addEventListener('toggle', function () {
            if (root.open) {
                refresh(root);
            }
        });
        setInterval(function () { refresh(root); }, 60000);
    });
})();
