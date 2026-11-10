/*
  Public / member notification bell.

  The markup is rendered server-side. This script polls the JSON feed so the
  badge stays fresh and rebuilds the list after the server changes. Opening an
  item follows its open_url, and the server marks it read before redirecting.
  The options menu mirrors the admin bell: mark every visible row read, or
  remove the ticked rows from the bell while keeping the record in history.
*/
(function () {
    'use strict';

    var REFRESH_MS = 60000;

    function el(tag, className) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        return node;
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
        var wrapper = el('div', 'notif-bell-row');

        var select = el('label', 'notif-bell-select');
        select.title = 'Select notification';
        var check = el('input');
        check.type = 'checkbox';
        check.value = item.id || '';
        check.setAttribute('data-sboi-public-check', '');
        check.setAttribute(
            'aria-label',
            'Select ' + (item.title || 'notification')
        );
        select.appendChild(check);

        var link = el(
            'a',
            'notif-item tone-' + (item.tone || 'info') +
                (item.unread ? ' is-unread' : '')
        );
        link.href = item.open_url || item.url || '#';
        link.setAttribute('data-notification-id', item.id || '');

        var title = el('span', 'notif-item-title');
        title.textContent = item.title || '';
        link.appendChild(title);

        if (item.body) {
            var desc = el('span', 'notif-item-desc');
            desc.textContent = item.body;
            link.appendChild(desc);
        }

        var date = el('span', 'notif-item-date');
        date.textContent = item.date || '';
        link.appendChild(date);

        wrapper.appendChild(select);
        wrapper.appendChild(link);
        return wrapper;
    }

    function empty() {
        var wrap = el('div', 'notif-empty');
        wrap.appendChild(icon());
        var text = el('span');
        text.textContent = "You're all caught up. No active notifications.";
        wrap.appendChild(text);
        return wrap;
    }

    function csrfToken(root) {
        var input = root.querySelector('[data-sboi-public-csrf]');
        if (input && input.value) {
            return input.value;
        }
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function selectedIds(root) {
        var list = root.querySelector('[data-sboi-public-list]');
        if (!list) {
            return [];
        }
        return Array.prototype.slice
            .call(list.querySelectorAll('[data-sboi-public-check]:checked'))
            .map(function (check) {
                return check.value;
            })
            .filter(Boolean);
    }

    function syncSelection(root) {
        var list = root.querySelector('[data-sboi-public-list]');
        var deleteBtn = root.querySelector(
            '[data-sboi-public-delete-selected]'
        );
        if (list) {
            Array.prototype.forEach.call(
                list.querySelectorAll('.notif-bell-row'),
                function (rowNode) {
                    var check = rowNode.querySelector(
                        '[data-sboi-public-check]'
                    );
                    rowNode.classList.toggle(
                        'is-selected',
                        Boolean(check && check.checked)
                    );
                }
            );
        }
        if (deleteBtn) {
            deleteBtn.disabled = selectedIds(root).length === 0;
        }
    }

    function render(root, data) {
        var list = root.querySelector('[data-sboi-public-list]');
        var badge = root.querySelector('[data-sboi-public-badge]');
        var markAllBtn = root.querySelector('[data-sboi-public-mark-all]');
        if (!list || !badge) {
            return;
        }

        badge.textContent = data.badge > 99 ? '99+' : String(data.badge || 0);
        badge.hidden = !data.badge;

        list.innerHTML = '';
        if (!data.items || !data.items.length) {
            list.appendChild(empty());
        } else {
            data.items.forEach(function (item) {
                list.appendChild(row(item));
            });
        }

        if (markAllBtn) {
            markAllBtn.disabled = !data.items || !data.items.length;
        }
        syncSelection(root);
    }

    function refresh(root) {
        var list = root.querySelector('[data-sboi-public-list]');
        var badge = root.querySelector('[data-sboi-public-badge]');
        if (!list || !badge) {
            return;
        }
        // A refresh that started before a bulk action must never re-render the
        // old row after that action has already completed.
        var seq = root._notifSeq = (root._notifSeq || 0) + 1;
        fetch(root.getAttribute('data-api-url'), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        }).then(function (data) {
            if (seq === root._notifSeq) {
                render(root, data);
            }
        }).catch(function () {
            /* Keep the server-rendered list and try again on the next tick. */
        });
    }

    function post(url, params, root) {
        var token = csrfToken(root);
        params.append('csrfmiddlewaretoken', token);
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': token,
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
            },
            body: params.toString()
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        });
    }

    function actionScope(button) {
        return (button && button.getAttribute('data-scope')) || '';
    }

    function closeMore(root) {
        var more = root.querySelector('.notif-bell-more');
        if (more) more.open = false;
    }

    function closeBell(root) {
        if (!root.open) return;
        root.open = false;
        closeMore(root);
    }

    function wire(root) {
        var list = root.querySelector('[data-sboi-public-list]');
        var markAllBtn = root.querySelector('[data-sboi-public-mark-all]');
        var deleteBtn = root.querySelector(
            '[data-sboi-public-delete-selected]'
        );

        root.addEventListener('toggle', function () {
            if (root.open) {
                refresh(root);
            } else {
                closeMore(root);
            }
        });

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
                post(markAllBtn.getAttribute('data-url'), params, root)
                    .then(function (data) {
                        root._notifSeq = (root._notifSeq || 0) + 1;
                        render(root, data);
                        closeMore(root);
                    })
                    .catch(function () {
                        markAllBtn.disabled = false;
                        syncSelection(root);
                    });
            });
        }

        if (deleteBtn) {
            deleteBtn.addEventListener('click', function () {
                var ids = selectedIds(root);
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
                post(deleteBtn.getAttribute('data-url'), params, root)
                    .then(function (data) {
                        root._notifSeq = (root._notifSeq || 0) + 1;
                        render(root, data);
                        closeMore(root);
                    })
                    .catch(function () {
                        /* Leave the rows as they are; the next poll retries. */
                    })
                    .then(function () {
                        syncSelection(root);
                    });
            });
        }

        if (list) {
            list.addEventListener('change', function (event) {
                if (
                    event.target &&
                    event.target.matches('[data-sboi-public-check]')
                ) {
                    syncSelection(root);
                }
            });
        }

        setInterval(function () {
            refresh(root);
        }, REFRESH_MS);

        // The account page updates read state without reloading. Ask the bell
        // to refresh its list and badge so both surfaces stay in sync.
        document.addEventListener('sboi:notifications-updated', function () {
            refresh(root);
        });
    }

    document.querySelectorAll('[data-sboi-public-bell]').forEach(wire);

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
})();
