(function () {
    'use strict';

    var overlay = null;
    var pendingDelete = { pks: [], across: false };

    function ensureOverlay() {
        if (overlay) {
            return overlay;
        }
        overlay = document.createElement('div');
        overlay.className = 'sboi-delete-overlay';
        overlay.innerHTML =
            '<div class="sboi-delete-backdrop" data-sboi-close></div>' +
            '<div class="sboi-delete-modal" role="alertdialog" aria-modal="true" aria-labelledby="sboi-delete-title">' +
                '<div class="sboi-delete-head">' +
                    '<div class="sboi-delete-icon">!</div>' +
                    '<h2 id="sboi-delete-title">Delete confirmation</h2>' +
                    '<button type="button" class="sboi-delete-x" data-sboi-close aria-label="Close">&times;</button>' +
                '</div>' +
                '<div class="sboi-delete-body"></div>' +
            '</div>';
        overlay.addEventListener('click', function (e) {
            if (e.target.closest('[data-sboi-close]')) {
                close();
            }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay.classList.contains('open')) {
                close();
            }
        });
        document.body.appendChild(overlay);
        return overlay;
    }

    function close() {
        if (overlay) {
            overlay.classList.remove('open');
        }
    }

    function landingUrl(submitUrl) {
        var qIndex = submitUrl.indexOf('?');
        var path = qIndex === -1 ? submitUrl : submitUrl.slice(0, qIndex);
        var qs = qIndex === -1 ? '' : submitUrl.slice(qIndex);
        var next = qs.match(/[?&]next=([^&]+)/);
        if (next) {
            return decodeURIComponent(next[1]);
        }
        path = path.replace(/\/[^/]+\/delete\/$/, '/');
        return path + qs;
    }

    function showError(body, message) {
        var msg = document.createElement('p');
        msg.className = 'sboi-delete-error';
        msg.textContent = message;
        body.appendChild(msg);
    }

    function pksFromUrl(url) {
        var path = url.replace(/\?.*$/, '');
        var m = path.match(/\/(\d+)\/delete\/$/);
        return m ? [m[1]] : [];
    }

    function removeRows(pks) {
        var table = document.getElementById('result_list');
        if (!table) {
            return 0;
        }
        var removed = 0;
        table.querySelectorAll('tbody tr').forEach(function (tr) {
            var cb = tr.querySelector('input.action-select');
            if (cb && pks.indexOf(cb.value) !== -1) {
                tr.remove();
                removed += 1;
            }
        });
        return removed;
    }

    function syncCounter(removed) {
        var remaining = document.querySelectorAll('#result_list input.action-select:checked').length;
        document.querySelectorAll('span.action-counter').forEach(function (counter) {
            var total = parseInt(counter.dataset.actionsIcnt || '0', 10);
            total = Math.max(0, total - removed);
            counter.dataset.actionsIcnt = String(total);
            counter.textContent = remaining + ' of ' + total + ' selected';
            counter.classList.remove('hidden');
        });
        var toggle = document.getElementById('action-toggle');
        if (toggle) {
            toggle.checked = false;
        }
        document.querySelectorAll('input.select-across').forEach(function (el) {
            el.value = '0';
        });
        document.querySelectorAll('div.actions span.question, div.actions span.clear, div.actions span.all').forEach(function (el) {
            el.classList.add('hidden');
            el.style.display = '';
        });
    }

    function handleSuccess(submitUrl) {
        var landing = landingUrl(submitUrl);
        if (pendingDelete.across || !document.getElementById('result_list')) {
            close();
            if (window.sboiNav) {
                window.sboiNav.load(landing, false);
            } else {
                window.location.href = landing;
            }
            return;
        }
        var removed = removeRows(pendingDelete.pks);
        close();
        if (!removed || !document.querySelector('#result_list tbody tr')) {
            if (window.sboiNav) {
                window.sboiNav.load(landing, false);
            } else {
                window.location.reload();
            }
            return;
        }
        syncCounter(removed);
    }

    function wire(root, submitUrl) {
        root.querySelectorAll('.btn-cancel').forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                close();
            });
        });
        var form = root.querySelector('form');
        if (!form) {
            return;
        }
        form.setAttribute('action', submitUrl);
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var btn = form.querySelector('input[type="submit"]');
            if (btn && btn.disabled) {
                return;
            }
            if (btn) {
                btn.disabled = true;
                btn.value = 'Deleting\u2026';
            }
            fetch(form.getAttribute('action'), {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: new FormData(form),
                redirect: 'manual'
            }).then(function (resp) {
                if (resp.type === 'opaqueredirect') {
                    handleSuccess(submitUrl);
                    return null;
                }
                if (resp.ok) {
                    return resp.text();
                }
                throw new Error('HTTP ' + resp.status);
            }).then(function (html) {
                if (html === null) {
                    return;
                }
                if (btn) {
                    btn.disabled = false;
                    btn.value = 'Yes, delete it';
                }
                var holder = document.createElement('div');
                holder.innerHTML = html;
                var popup = holder.querySelector('.sboi-popup');
                var body = overlay.querySelector('.sboi-delete-body');
                if (popup) {
                    wire(popup, submitUrl);
                    body.innerHTML = '';
                    body.appendChild(popup);
                } else {
                    showError(body, "Couldn't complete the delete. Try again.");
                }
            }).catch(function () {
                if (btn) {
                    btn.disabled = false;
                    btn.value = 'Yes, delete it';
                }
                showError(overlay.querySelector('.sboi-delete-body'), "Couldn't complete the delete. Try again.");
            });
        });
    }

    function loadInto(ov, fetchPromise, submitUrl) {
        var body = ov.querySelector('.sboi-delete-body');
        body.innerHTML = '<p class="sboi-delete-loading">Loading\u2026</p>';
        ov.classList.add('open');
        fetchPromise.then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.text();
        }).then(function (html) {
            var holder = document.createElement('div');
            holder.innerHTML = html;
            var popup = holder.querySelector('.sboi-popup');
            if (!popup) {
                throw new Error('no popup content');
            }
            wire(popup, submitUrl);
            body.innerHTML = '';
            body.appendChild(popup);
        }).catch(function () {
            body.innerHTML = '<p class="sboi-delete-msg">Couldn\u2019t load the confirmation.</p>';
        });
    }

    document.addEventListener('click', function (e) {
        var link = e.target.closest ? e.target.closest('a.deletelink, a[href*="/delete/"]') : null;
        if (link) {
            e.preventDefault();
            pendingDelete.pks = pksFromUrl(link.href);
            pendingDelete.across = false;
            var ov = ensureOverlay();
            loadInto(ov, fetch(link.href, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            }), link.href);
        }
    });

    function wireChangelistPage() {
    var form = document.getElementById('changelist-form');
    if (form) {
        form.addEventListener('submit', function (e) {
            var select = form.querySelector('select[name="action"]');
            if (!select || select.value !== 'delete_selected') {
                return;
            }
            var picked = form.querySelectorAll('input[name="_selected_action"]:checked');
            if (!picked.length) {
                return;
            }
            e.preventDefault();
            pendingDelete.pks = Array.prototype.map.call(picked, function (el) {
                return el.value;
            });
            var across = form.querySelector('input.select-across');
            pendingDelete.across = !!(across && across.value === '1');
            var url = (form.getAttribute('action') || window.location.pathname).split('?')[0];
            var ov = ensureOverlay();
            loadInto(ov, fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: new FormData(form)
            }), url);
        });
    }

    var table = document.getElementById('result_list');
    if (table) {
        var headRow = table.querySelector('thead tr');
        var rows = table.querySelectorAll('tbody tr');
        if (headRow && rows.length) {
            var clForm = document.getElementById('changelist-form');
            var base = (clForm && clForm.getAttribute('action'))
                ? clForm.getAttribute('action').split('?')[0]
                : window.location.pathname.split('?')[0];
            var preserved = window.location.search
                ? '?_changelist_filters=' + encodeURIComponent(window.location.search.slice(1))
                : '';
            var th = document.createElement('th');
            th.scope = 'col';
            th.className = 'sboi-row-actions-head';
            th.textContent = 'Actions';
            headRow.appendChild(th);
            rows.forEach(function (tr) {
                var cb = tr.querySelector('input.action-select');
                if (!cb) {
                    return;
                }
                var td = document.createElement('td');
                td.className = 'sboi-row-actions';
                var edit = document.createElement('a');
                edit.href = base + cb.value + '/change/' + preserved;
                edit.textContent = 'Edit';
                edit.title = 'Edit';
                var del = document.createElement('a');
                del.href = base + cb.value + '/delete/' + preserved;
                del.className = 'sboi-row-delete';
                del.textContent = 'Delete';
                del.title = 'Delete';
                td.appendChild(edit);
                td.appendChild(del);
                tr.appendChild(td);
            });
        }
    }
}

wireChangelistPage();
document.addEventListener('sboi:admin-loaded', wireChangelistPage);
})();