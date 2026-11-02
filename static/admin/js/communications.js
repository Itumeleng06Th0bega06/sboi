/*
  Admin Communications portal.

  Progressive enhancement only: every link and form still works without
  JavaScript. With JS enabled, conversation switching, sending, polling and
  search use the server-rendered HTML fragments instead of full page loads.
  No WebSockets, Redis or Celery are required.
*/
(function () {
    'use strict';

    var root = document.querySelector('[data-comms-root]');
    if (!root) {
        return;
    }

    var inboxUrl = root.getAttribute('data-inbox-url') || '/';
    var listUrl = root.getAttribute('data-list-url');
    var listContainer = root.querySelector('[data-comms-conversation-list]');
    var workspace = root.querySelector('[data-comms-workspace]');
    var POLL_MS = 15000;
    var LIST_REFRESH_MS = 25000;

    function qs(selector, scope) {
        return (scope || root).querySelector(selector);
    }

    function qsa(selector, scope) {
        return Array.prototype.slice.call((scope || root).querySelectorAll(selector));
    }

    function activeConversationId() {
        var active = qs('.comms-conversation.is-active');
        return active ? active.getAttribute('data-conversation-id') : '';
    }

    function currentQuery() {
        var input = qs('[data-comms-list-search] input[name="q"]');
        return input ? input.value.trim() : '';
    }

    function showError(form, message) {
        var box = qs('[data-comms-error]', form);
        if (!box) {
            return;
        }
        box.textContent = message;
        box.hidden = !message;
    }

    function scrollToBottom(force) {
        var messages = qs('[data-comms-messages]');
        if (!messages) {
            return;
        }
        if (force || messages.scrollHeight - messages.scrollTop - messages.clientHeight < 90) {
            messages.scrollTop = messages.scrollHeight;
        }
    }

    function updateLastId() {
        var messages = qs('[data-comms-messages]');
        if (!messages) {
            return;
        }
        var items = qsa('.comms-message', messages);
        if (items.length) {
            messages.setAttribute('data-last-id', items[items.length - 1].getAttribute('data-message-id'));
        }
    }

    function setActive(id) {
        qsa('.comms-conversation').forEach(function (link) {
            link.classList.toggle('is-active', link.getAttribute('data-conversation-id') === String(id));
        });
    }

    function clearReply(form) {
        var input = qs('[data-comms-reply-input]', form);
        var preview = qs('[data-comms-reply-preview]', form);
        var text = qs('.comms-reply-preview__text', preview || form);
        if (input) {
            input.value = '';
        }
        if (preview) {
            preview.hidden = true;
        }
        if (text) {
            text.textContent = '';
        }
    }

    function resetComposer(form) {
        var textarea = qs('[data-comms-textarea]', form);
        var file = qs('[data-comms-file]', form);
        if (textarea) {
            textarea.value = '';
            textarea.style.height = '';
        }
        if (file) {
            file.value = '';
        }
        var hint = qs('[data-comms-file-hint]', form);
        if (hint) {
            hint.textContent = '';
        }
        clearReply(form);
        showError(form, '');
    }

    function conversationUrl(id) {
        return inboxUrl + '?conversation=' + encodeURIComponent(id);
    }

    function openConversation(workspaceUrl, fullUrl, id, push) {
        if (!workspace || !workspaceUrl) {
            window.location.href = fullUrl;
            return;
        }
        root.classList.add('comms-loading');
        fetch(workspaceUrl, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.text();
        }).then(function (html) {
            workspace.innerHTML = html;
            workspace.classList.remove('comms-workspace--empty');
            root.classList.add('has-selection');
            setActive(id);
            // Opening the thread marks it read on the server. Refresh the
            // list now so the row's unread badge disappears immediately
            // instead of waiting for the 25-second list poll.
            refreshList();
            if (push !== false) {
                history.pushState({ conversation: id }, '', fullUrl);
            }
            var info = qs('[data-comms-info]', workspace);
            if (info) {
                info.classList.remove('is-open');
            }
            updateLastId();
            scrollToBottom(true);
            var textarea = qs('[data-comms-textarea]', workspace);
            if (textarea && window.matchMedia('(min-width: 761px)').matches) {
                textarea.focus();
            }
        }).catch(function () {
            window.location.href = fullUrl;
        }).finally(function () {
            root.classList.remove('comms-loading');
        });
    }

    function refreshList(preserveFocus) {
        if (!listUrl || !listContainer) {
            return;
        }
        var url = listUrl + '?q=' + encodeURIComponent(currentQuery());
        var id = activeConversationId();
        if (id) {
            url += '&conversation=' + encodeURIComponent(id);
        }
        var focused = preserveFocus && document.activeElement;
        fetch(url, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.text();
        }).then(function (html) {
            var hadFocus = focused && listContainer.contains(focused);
            listContainer.innerHTML = html;
            if (hadFocus) {
                var input = qs('[data-comms-list-search] input[name="q"]');
                if (input) {
                    input.focus();
                }
            }
        }).catch(function () {
            /* Keep the current list on a transient network error. */
        });
    }

    function sendMessage(form) {
        var textarea = qs('[data-comms-textarea]', form);
        var file = qs('[data-comms-file]', form);
        var body = textarea ? textarea.value.trim() : '';
        if (!body && (!file || !file.files.length)) {
            showError(form, 'Write a message or attach a file.');
            if (textarea) {
                textarea.focus();
            }
            return;
        }
        var button = qs('button[type="submit"]', form);
        if (button) {
            button.disabled = true;
        }
        showError(form, '');
        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            return response.text().then(function (text) {
                if (!response.ok) {
                    var message = 'The message could not be sent.';
                    try {
                        message = JSON.parse(text).error || message;
                    } catch (error) {
                        /* Fall back to the generic message. */
                    }
                    throw new Error(message);
                }
                return text;
            });
        }).then(function (html) {
            var messages = qs('[data-comms-messages]');
            if (!messages) {
                return;
            }
            var empty = qs('.comms-thread-empty', messages);
            if (empty) {
                empty.remove();
            }
            messages.insertAdjacentHTML('beforeend', html);
            resetComposer(form);
            updateLastId();
            scrollToBottom(true);
            refreshList();
        }).catch(function (error) {
            showError(form, error.message || 'The message could not be sent.');
        }).finally(function () {
            if (button) {
                button.disabled = false;
            }
        });
    }

    function searchThread(form) {
        var url = form.getAttribute('data-workspace-url');
        var input = qs('input[name="mq"]', form);
        if (!url) {
            return;
        }
        var query = input ? input.value.trim() : '';
        root.classList.add('comms-loading');
        fetch(url + '?mq=' + encodeURIComponent(query), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.text();
        }).then(function (html) {
            workspace.innerHTML = html;
            workspace.classList.remove('comms-workspace--empty');
            root.classList.add('has-selection');
            updateLastId();
            scrollToBottom(true);
        }).catch(function () {
            form.submit();
        }).finally(function () {
            root.classList.remove('comms-loading');
        });
    }

    function pollMessages() {
        if (document.hidden) {
            return;
        }
        var messages = qs('[data-comms-messages]');
        if (!messages || !messages.getAttribute('data-poll-url')) {
            return;
        }
        var search = qs('[data-comms-thread-search] input[name="mq"]');
        if (search && search.value.trim()) {
            return;
        }
        var url = messages.getAttribute('data-poll-url');
        var nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 90;
        fetch(url, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.text();
        }).then(function (html) {
            if (messages.innerHTML !== html) {
                messages.innerHTML = html;
                updateLastId();
                if (nearBottom) {
                    scrollToBottom(true);
                }
            }
        }).catch(function () {
            /* A later poll will retry; the composer remains usable. */
        });
    }

    function autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 140) + 'px';
    }

    var listSearchTimer = null;
    root.addEventListener('input', function (event) {
        if (event.target.matches('[data-comms-list-search] input[name="q"]')) {
            window.clearTimeout(listSearchTimer);
            listSearchTimer = window.setTimeout(function () {
                refreshList(true);
            }, 300);
        }
    });

    root.addEventListener('change', function (event) {
        if (!event.target.matches('[data-comms-file]')) {
            return;
        }
        var file = event.target.files && event.target.files[0];
        var hint = qs('[data-comms-file-hint]', event.target.closest('form'));
        if (hint) {
            hint.textContent = file ? file.name : '';
        }
        if (file && file.size > 10 * 1024 * 1024) {
            showError(event.target.closest('form'), 'Attachments must be 10 MB or smaller.');
        }
    });

    root.addEventListener('keydown', function (event) {
        var textarea = event.target;
        if (!textarea.matches('[data-comms-textarea]')) {
            return;
        }
        autoResize(textarea);
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            var form = textarea.closest('form');
            if (form) {
                form.requestSubmit();
            }
        }
    });

    root.addEventListener('click', function (event) {
        var openButton = event.target.closest('[data-comms-dialog-open]');
        if (openButton) {
            var dialog = qs('[data-comms-dialog="' + openButton.getAttribute('data-comms-dialog-open') + '"]');
            if (dialog) {
                if (typeof dialog.showModal === 'function') {
                    dialog.showModal();
                } else {
                    dialog.setAttribute('open', '');
                }
            }
            return;
        }

        var closeButton = event.target.closest('[data-comms-dialog-close]');
        if (closeButton) {
            var parentDialog = closeButton.closest('dialog');
            if (parentDialog) {
                if (typeof parentDialog.close === 'function') {
                    parentDialog.close();
                } else {
                    parentDialog.removeAttribute('open');
                }
            }
            return;
        }

        var conversationLink = event.target.closest('[data-comms-open]');
        if (conversationLink) {
            event.preventDefault();
            openConversation(
                conversationLink.getAttribute('data-workspace-url'),
                conversationLink.href,
                conversationLink.getAttribute('data-conversation-id')
            );
            return;
        }

        if (event.target.closest('[data-comms-back]')) {
            event.preventDefault();
            root.classList.remove('has-selection');
            history.pushState({}, '', inboxUrl);
            return;
        }

        if (event.target.closest('[data-comms-info-toggle]')) {
            var info = qs('[data-comms-info]');
            if (info) {
                info.classList.add('is-open');
            }
            return;
        }

        if (event.target.closest('[data-comms-info-close]')) {
            var openInfo = qs('[data-comms-info]');
            if (openInfo) {
                openInfo.classList.remove('is-open');
            }
            return;
        }

        var replyButton = event.target.closest('[data-comms-reply]');
        if (replyButton) {
            var form = qs('[data-comms-send]');
            if (!form) {
                return;
            }
            var replyInput = qs('[data-comms-reply-input]', form);
            var preview = qs('[data-comms-reply-preview]', form);
            var text = preview ? qs('.comms-reply-preview__text', preview) : null;
            if (replyInput) {
                replyInput.value = replyButton.getAttribute('data-message-id');
            }
            if (text) {
                text.textContent = 'Replying to ' + replyButton.getAttribute('data-sender');
            }
            if (preview) {
                preview.hidden = false;
            }
            var composer = qs('[data-comms-textarea]', form);
            if (composer) {
                composer.focus();
            }
            return;
        }

        if (event.target.closest('[data-comms-reply-cancel]')) {
            var sendForm = qs('[data-comms-send]');
            if (sendForm) {
                clearReply(sendForm);
            }
            return;
        }

        if (event.target.closest('[data-comms-scroll-bottom]')) {
            scrollToBottom(true);
            return;
        }
    });

    root.addEventListener('submit', function (event) {
        var form = event.target;
        if (form.matches('[data-comms-send]')) {
            event.preventDefault();
            sendMessage(form);
            return;
        }
        if (form.matches('[data-comms-list-search]')) {
            event.preventDefault();
            refreshList(false);
            return;
        }
        if (form.matches('[data-comms-thread-search]')) {
            event.preventDefault();
            searchThread(form);
        }
    });

    window.addEventListener('popstate', function () {
        var params = new URL(window.location.href).searchParams;
        var id = params.get('conversation');
        if (!id) {
            root.classList.remove('has-selection');
            return;
        }
        var link = qs('[data-conversation-id="' + id + '"]');
        if (link) {
            openConversation(
                link.getAttribute('data-workspace-url'),
                link.href,
                id,
                false
            );
        }
    });

    window.setInterval(pollMessages, POLL_MS);
    window.setInterval(function () {
        if (!document.hidden) {
            refreshList(false);
        }
    }, LIST_REFRESH_MS);

    qsa('dialog[data-auto-open]').forEach(function (dialog) {
        if (typeof dialog.showModal === 'function') {
            dialog.showModal();
        } else {
            dialog.setAttribute('open', '');
        }
    });

    updateLastId();
    scrollToBottom(true);
})();
