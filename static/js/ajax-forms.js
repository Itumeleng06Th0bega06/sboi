(function () {
    'use strict';

    function showPopup(message, isError) {
        var old = document.querySelector('.ajax-popup');
        if (old) {
            old.remove();
        }
        var popup = document.createElement('div');
        popup.className = 'ajax-popup' + (isError ? ' error' : '');
        popup.setAttribute('role', 'status');
        popup.textContent = message;
        document.body.appendChild(popup);
        setTimeout(function () {
            popup.classList.add('hide');
        }, 3200);
        setTimeout(function () {
            popup.remove();
        }, 3800);
    }

    document.addEventListener('submit', function (e) {
        var form = e.target.closest ? e.target.closest('form[data-ajax-form]') : null;
        if (!form) {
            return;
        }
        e.preventDefault();
        var btn = form.querySelector('button[type="submit"]');
        var original = btn ? btn.textContent : '';
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Sending\u2026';
        }
        function restore() {
            if (btn) {
                btn.disabled = false;
                btn.textContent = original;
            }
        }
        fetch(form.action, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: new FormData(form)
        }).then(function (resp) {
            return resp.json().catch(function () {
                throw new Error('invalid response');
            }).then(function (data) {
                if (resp.ok && data.ok) {
                    form.reset();
                    showPopup(data.message || 'Thank you!', false);
                } else {
                    showPopup(data.message || 'Something went wrong. Please try again.', true);
                }
            });
        }).catch(function () {
            showPopup('Could not send. Please try again.', true);
        }).then(restore, restore);
    });
})();