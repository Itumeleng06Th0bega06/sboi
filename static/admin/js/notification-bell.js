/*
  Admin notification bell.

  The bell markup (button, badge, list and footer) is rendered server-side by
  admin/base_site.html; this script only refreshes it from the JSON endpoint so
  badge counts stay current without a full page reload.
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

    function row(item) {
        var a = el('a', 'sboi-bell-item tone-' + item.tone);
        a.href = item.url;

        var iconWrap = el('span', 'sboi-bell-icon');
        iconWrap.appendChild(icon(item.icon));

        var label = el('span', 'sboi-bell-label');
        label.textContent = item.label;

        var count = el('span', 'sboi-bell-count' + (item.count === 0 ? ' zero' : ''));
        count.textContent = String(item.count);

        a.appendChild(iconWrap);
        a.appendChild(label);
        a.appendChild(count);
        return a;
    }

    function render(data) {
        if (!badge || !list) {
            return;
        }

        if (data.badge > 0) {
            badge.textContent = data.badge > 99 ? '99+' : String(data.badge);
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }

        list.innerHTML = '';
        if (!data.items || !data.items.length) {
            var empty = el('div', 'sboi-bell-empty');
            empty.appendChild(icon('bell-off'));
            var emptyText = el('span');
            emptyText.textContent = 'You\u2019re all caught up.';
            empty.appendChild(emptyText);
            list.appendChild(empty);
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

    bell.addEventListener('toggle', function () {
        if (bell.open) {
            refresh();
        }
    });

    refresh();
    setInterval(refresh, REFRESH_MS);
    document.addEventListener('sboi:admin-loaded', refresh);
})();
