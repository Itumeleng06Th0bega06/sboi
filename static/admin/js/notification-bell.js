/*
  Admin notification bell.

  The bell markup is rendered server-side by admin/base_site.html. This script
  refreshes it from the JSON endpoint and powers the two bulk actions in the
  options menu: mark every visible row read, and remove the ticked rows from
  the bell (the notification record itself is kept for the history page).
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
    var csrfInput = bell.querySelector('[data-sboi-bell-csrf]');
    var markAllBtn = bell.querySelector('[data-sboi-bell-mark-all]');
    var deleteBtn = bell.querySelector('[data-sboi-bell-delete-selected]');
    var REFRESH_MS = 60000;
    // A refresh that started before a bulk action must never re-render the
    // old row after that action has already completed.
    var requestSeq = 0;

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

    function csrfToken() {
        if (csrfInput && csrfInput.value) {
            return csrfInput.value;
        }
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function row(item) {
        var wrapper = el('div', 'sboi-bell-row');

        var select = el('label', 'sboi-bell-select');
        select.title = 'Select notification';
        var check = el('input');
        check.type = 'checkbox';
        check.value = item.id || '';
        check.setAttribute('data-sboi-bell-check', '');
        check.setAttribute(
            'aria-label',
            'Select ' + (item.title || item.label || 'notification')
        );
        select.appendChild(check);

        var link = el(
            'a',
            'sboi-bell-item tone-' + (item.tone || 'info') + (item.unread ? ' is-unread' : '')
        );
        link.href = item.open_url || item.url || '#';
        link.setAttribute('data-notification-id', item.id || '');

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

        wrapper.appendChild(select);
        wrapper.appendChild(link);
        return wrapper;
    }

    function emptyState() {
        var empty = el('div', 'sboi-bell-empty');
        empty.appendChild(icon('bell-off'));
        var text = el('span');
        text.textContent = "You're all caught up. No active notifications.";
        empty.appendChild(text);
        return empty;
    }

    function selectedIds() {
        if (!list) {
            return [];
        }
        return Array.prototype.slice
            .call(list.querySelectorAll('[data-sboi-bell-check]:checked'))
            .map(function (check) {
                return check.value;
            })
            .filter(Boolean);
    }

    function syncSelection() {
        if (list) {
            Array.prototype.forEach.call(
                list.querySelectorAll('.sboi-bell-row'),
                function (rowNode) {
                    var check = rowNode.querySelector('[data-sboi-bell-check]');
                    rowNode.classList.toggle(
                        'is-selected',
                        Boolean(check && check.checked)
                    );
                }
            );
        }
        if (deleteBtn) {
            deleteBtn.disabled = selectedIds().length === 0;
        }
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
        } else {
            data.items.forEach(function (item) {
                list.appendChild(row(item));
            });
        }

        if (markAllBtn) {
            markAllBtn.disabled = !data.items || !data.items.length;
        }
        syncSelection();
    }

    function refresh() {
        var seq = ++requestSeq;
        fetch(apiUrl, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.json();
        }).then(function (data) {
            if (seq === requestSeq) {
                render(data);
            }
        }).catch(function () {
            /* Keep the server-rendered rows and retry on the next tick. */
        });
    }

    function post(url, params) {
        params.append('csrfmiddlewaretoken', csrfToken());
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken(),
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
            },
            body: params.toString()
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.json();
        });
    }

    function closeMore() {
        var more = bell.querySelector('.sboi-bell-more');
        if (more) more.open = false;
    }

    function actionScope(button) {
        return (button && button.getAttribute('data-scope')) || '';
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', function () {
            if (markAllBtn.disabled) {
                return;
            }
            var params = new URLSearchParams();
            var scope = actionScope(markAllBtn);
            if (scope) {
                params.append('scope', scope);
            }
            markAllBtn.disabled = true;
            post(markAllBtn.getAttribute('data-url'), params)
                .then(function (data) {
                    requestSeq += 1;
                    render(data);
                    closeMore();
                })
                .catch(function () {
                    markAllBtn.disabled = false;
                    syncSelection();
                });
        });
    }

    if (deleteBtn) {
        deleteBtn.addEventListener('click', function () {
            var ids = selectedIds();
            if (!ids.length) {
                return;
            }
            var params = new URLSearchParams();
            ids.forEach(function (id) {
                params.append('ids', id);
            });
            var scope = actionScope(deleteBtn);
            if (scope) {
                params.append('scope', scope);
            }
            deleteBtn.disabled = true;
            post(deleteBtn.getAttribute('data-url'), params)
                .then(function (data) {
                    requestSeq += 1;
                    render(data);
                    closeMore();
                })
                .catch(function () {
                    /* Leave the rows as they are; the next poll retries. */
                })
                .then(syncSelection);
        });
    }

    if (list) {
        list.addEventListener('change', function (event) {
            if (event.target && event.target.matches('[data-sboi-bell-check]')) {
                syncSelection();
            }
        });
    }

    bell.addEventListener('toggle', function () {
        if (bell.open) {
            refresh();
        } else {
            closeMore();
        }
    });

    document.addEventListener('click', function (event) {
        if (bell.open && !bell.contains(event.target)) {
            bell.open = false;
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && bell.open) {
            bell.open = false;
        }
    });

    refresh();
    setInterval(refresh, REFRESH_MS);
    document.addEventListener('sboi:admin-loaded', refresh);
})();
