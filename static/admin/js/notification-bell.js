/*
  Admin notification bell.

  The bell markup is rendered server-side by admin/base_site.html. This script
  refreshes it from the JSON endpoint and sends per-user read/dismiss actions
  without reloading the page.
*/
(function () {
    'use strict';

    var bell = document.querySelector('[data-sboi-bell]');
    if (!bell) {
        return;
    }

    var apiUrl = bell.getAttribute('data-api-url');
    var badge = bell.querySelector('[data-sboi-bell-badge]');
    var list = bell.querySelector('[data-sboi-bell-list]');
    var REFRESH_MS = 60000;

    function el(tag, className) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        return node;
    }

    function csrfToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function icon(name) {
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'sboi-ico');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        var use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        use.setAttribute('href', '#sboi-i-' + name);
        svg.appendChild(use);
        return svg;
    }

    function actionButton(label, url) {
        var button = el('button', 'sboi-bell-action');
        button.type = 'button';
        button.setAttribute('data-sboi-bell-action', url || '');
        button.textContent = label;
        return button;
    }

    function row(item) {
        var wrap = el('div', 'sboi-bell-item tone-' + (item.tone || 'info'));

        var link = el('a', 'sboi-bell-item__link');
        link.href = item.url || '#';

        var iconWrap = el('span', 'sboi-bell-icon');
        iconWrap.appendChild(icon(item.icon || 'bell'));

        var copy = el('span', 'sboi-bell-copy');
        var title = el('span', 'sboi-bell-label');
        title.textContent = item.title || item.label || '';
        copy.appendChild(title);

        if (item.body) {
            var desc = el('span', 'sboi-bell-desc');
            desc.textContent = item.body;
            copy.appendChild(desc);
        }

        var date = el('span', 'sboi-bell-date');
        date.textContent = item.date || '';
        copy.appendChild(date);

        link.appendChild(iconWrap);
        link.appendChild(copy);
        wrap.appendChild(link);

        var actions = el('span', 'sboi-bell-actions');
        if (item.unread) {
            actions.appendChild(actionButton('Mark read', item.mark_read_url));
        }
        actions.appendChild(actionButton('Dismiss', item.dismiss_url));
        wrap.appendChild(actions);
        return wrap;
    }

    function emptyState() {
        var empty = el('div', 'sboi-bell-empty');
        empty.appendChild(icon('bell-off'));
        var text = el('span');
        text.textContent = "You're all caught up. No active notifications.";
        empty.appendChild(text);
        return empty;
    }

    function render(data) {
        if (!badge || !list) {
            return;
        }

        badge.textContent = data.badge > 99 ? '99+' : String(data.badge || 0);
        badge.hidden = !data.badge;

        list.innerHTML = '';
        if (!data.items || !data.items.length) {
            list.appendChild(emptyState());
            return;
        }

        data.items.forEach(function (item) {
            list.appendChild(row(item));
        });
    }

    function refresh() {
        fetch(apiUrl, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.json();
        }).then(render).catch(function () {
            /* Keep the server-rendered rows and retry on the next tick. */
        });
    }

    function act(url, button) {
        if (!url) {
            return;
        }
        button.disabled = true;
        fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken()
            }
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.json();
        }).then(function () {
            refresh();
        }).catch(function () {
            button.disabled = false;
        });
    }

    bell.addEventListener('click', function (event) {
        var button = event.target.closest('[data-sboi-bell-action]');
        if (!button) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        act(button.getAttribute('data-sboi-bell-action'), button);
    });

    bell.addEventListener('toggle', function () {
        if (bell.open) {
            refresh();
        }
    });

    refresh();
    setInterval(refresh, REFRESH_MS);
    document.addEventListener('sboi:admin-loaded', refresh);
})();
