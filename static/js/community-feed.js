/*
  Community feed progressive enhancement.

  Every form still submits normally without JavaScript. With JavaScript the
  composer, reactions, comments and removals stay on the page so the feed feels
  like a small social feed rather than a series of full page reloads.
*/
(function () {
    'use strict';

    var MAX_FILE_BYTES = 25 * 1024 * 1024;
    var POLL_MS = 30000;

    function qs(selector, scope) {
        return (scope || document).querySelector(selector);
    }

    function qsa(selector, scope) {
        return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
    }

    function showError(box, message) {
        if (!box) {
            return;
        }
        box.textContent = message || '';
        box.hidden = !message;
    }

    function resetComposer(form) {
        var body = qs('[data-feed-textarea]', form);
        var title = qs('.comms-compose-card__title', form);
        var file = qs('[data-feed-file]', form);
        var name = qs('[data-feed-file-name]', form);
        if (body) {
            body.value = '';
            body.style.height = '';
        }
        if (title) {
            title.value = '';
        }
        if (file) {
            file.value = '';
        }
        if (name) {
            name.textContent = '';
        }
        showError(qs('[data-feed-error]', form), '');
    }

    function autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }

    function setLatestId(root, id) {
        if (root && id) {
            root.setAttribute('data-feed-latest-id', String(id));
        }
    }

    function jsonRequest(url, options) {
        return fetch(url, options).then(function (response) {
            return response.text().then(function (text) {
                var data = {};
                try {
                    data = text ? JSON.parse(text) : {};
                } catch (error) {
                    data = {};
                }
                if (!response.ok) {
                    throw new Error(data.message || data.error || 'Something went wrong. Please try again.');
                }
                return data;
            });
        });
    }

    function submitComposer(form) {
        var body = qs('[data-feed-textarea]', form);
        var title = qs('.comms-compose-card__title', form);
        var file = qs('[data-feed-file]', form);
        var errorBox = qs('[data-feed-error]', form);
        var text = body ? body.value.trim() : '';
        var heading = title ? title.value.trim() : '';
        var upload = file && file.files && file.files[0];

        if (!text && !heading && !upload) {
            showError(errorBox, 'Write something or attach a file before posting.');
            if (body) {
                body.focus();
            }
            return;
        }
        if (upload && upload.size > MAX_FILE_BYTES) {
            showError(errorBox, 'Attachments must be 25 MB or smaller.');
            return;
        }

        var button = qs('button[type="submit"]', form);
        if (button) {
            button.disabled = true;
        }
        showError(errorBox, '');

        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            var root = form.closest('[data-feed-root]') || document;
            var list = qs('[data-feed-list]', root);
            if (list && data.html) {
                var empty = qs('[data-feed-empty]', list);
                if (empty) {
                    empty.remove();
                }
                list.insertAdjacentHTML('afterbegin', data.html);
                var post = list.firstElementChild;
                if (post && post.scrollIntoView) {
                    post.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }
            setLatestId(root, data.post_id);
            resetComposer(form);
        }).catch(function (error) {
            showError(errorBox, error.message);
        }).finally(function () {
            if (button) {
                button.disabled = false;
            }
        });
    }

    function closeReactionPicker(form) {
        if (!form) {
            return;
        }
        form.classList.remove('is-open');
        form.classList.remove('cf-reactions--open');
        form.classList.remove('comms-reactions--open');
        var toggle = qs('[data-cf-reaction-toggle]', form);
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
        }
    }

    function openReactionPicker(form) {
        if (!form) {
            return;
        }
        qsa('[data-feed-reaction].is-open').forEach(function (other) {
            if (other !== form) {
                closeReactionPicker(other);
            }
        });
        form.classList.add('is-open');
        var toggle = qs('[data-cf-reaction-toggle]', form);
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'true');
        }
    }

    function reactionTotal(form) {
        var total = 0;
        qsa('[data-reaction]', form).forEach(function (button) {
            var countNode = qs('[data-reaction-count]', button);
            total += parseInt(countNode ? countNode.textContent : '', 10) || 0;
        });
        return total;
    }

    function updateReactionTrigger(form, mine) {
        var toggle = qs('[data-cf-reaction-toggle]', form);
        if (!toggle) {
            return;
        }
        var current = qs('[data-cf-react-emoji]', toggle);
        var totalNode = qs('[data-cf-react-total]', toggle);
        var active = null;
        qsa('[data-reaction]', form).forEach(function (button) {
            if (mine.indexOf(button.getAttribute('data-reaction')) !== -1) {
                active = button;
            }
        });
        toggle.classList.toggle('has-reaction', !!active);
        if (current) {
            var emoji = active
                ? qs('.cf-react-emoji, .comms-reaction__emoji', active)
                : null;
            current.textContent = emoji ? emoji.textContent.trim() : '';
        }
        if (totalNode) {
            var total = reactionTotal(form);
            totalNode.textContent = total ? String(total) : '';
        }
        toggle.setAttribute(
            'aria-label', active ? 'Change reaction' : 'Add reaction'
        );
    }

    function bumpReactionTrigger(form) {
        var toggle = qs('[data-cf-reaction-toggle]', form);
        if (!toggle) {
            return;
        }
        toggle.classList.remove('is-bumping');
        // Force a reflow so picking another reaction replays the animation.
        void toggle.offsetWidth;
        toggle.classList.add('is-bumping');
        var clear = function (event) {
            if (event.target !== toggle) {
                return;
            }
            toggle.classList.remove('is-bumping');
            toggle.removeEventListener('animationend', clear);
        };
        toggle.addEventListener('animationend', clear);
    }

    function updateReactions(form, data) {
        var summary = data.summary || {};
        var mine = data.mine || [];
        qsa('[data-reaction]', form).forEach(function (button) {
            var key = button.getAttribute('data-reaction');
            var active = mine.indexOf(key) !== -1;
            var count = summary[key] || 0;
            var countNode = qs('[data-reaction-count]', button);
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
            if (countNode) {
                countNode.textContent = count ? String(count) : '';
            }
        });
        updateReactionTrigger(form, mine);
    }

    function submitReaction(form, submitter) {
        // FormData(form) omits the button that triggered the submit, so the
        // reaction value has to be appended explicitly.
        if (submitter) {
            qsa('.is-picked', form).forEach(function (button) {
                button.classList.remove('is-picked');
            });
            submitter.classList.add('is-picked');
        }
        var body = new FormData(form);
        if (submitter && submitter.name) {
            body.append(submitter.name, submitter.value || '');
        }
        jsonRequest(form.action, {
            method: 'POST',
            body: body,
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            updateReactions(form, data);
            // WhatsApp flow: the tray closes as soon as a reaction is chosen.
            closeReactionPicker(form);
            bumpReactionTrigger(form);
        }).catch(function () {
            form.submit();
        });
    }

    function submitComment(form) {
        var input = qs('input[name="body"]', form);
        var errorBox = qs('[data-feed-comment-error]', form.parentNode || form);
        var body = input ? input.value.trim() : '';
        if (!body) {
            showError(errorBox, 'Write a comment before sending.');
            if (input) {
                input.focus();
            }
            return;
        }

        var button = qs('button[type="submit"]', form);
        if (button) {
            button.disabled = true;
        }
        showError(errorBox, '');

        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            if (data.html) {
                form.insertAdjacentHTML('beforebegin', data.html);
            }
            if (input) {
                input.value = '';
            }
            var post = form.closest('[data-feed-post]');
            var count = qs('[data-comment-count]', post || document);
            if (count) {
                count.textContent = '💬 ' + (data.count || 0);
            }
        }).catch(function (error) {
            showError(errorBox, error.message);
        }).finally(function () {
            if (button) {
                button.disabled = false;
            }
        });
    }

    function removePost(form) {
        if (!window.confirm('Remove this post?')) {
            return;
        }
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function () {
            var post = form.closest('[data-feed-post]');
            if (post) {
                post.classList.add('is-removing');
                window.setTimeout(function () {
                    post.remove();
                }, 180);
            }
        }).catch(function () {
            form.submit();
        });
    }

    function removeComment(form) {
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            var comment = form.closest('[data-feed-comment-item]');
            if (comment) {
                comment.remove();
            }
            var post = form.closest('[data-feed-post]');
            var count = qs('[data-comment-count]', post || document);
            if (count) {
                count.textContent = '💬 ' + (data.count || 0);
            }
        }).catch(function () {
            form.submit();
        });
    }

    // -----------------------------------------------------------------------
    // Member community surface
    // -----------------------------------------------------------------------

    var toastTimer = null;

    function showToast(message, isError) {
        var toast = qs('[data-cf-toast]');
        if (!toast || !message) return;
        toast.textContent = message;
        toast.classList.toggle('is-error', !!isError);
        toast.hidden = false;
        if (toastTimer) window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            toast.hidden = true;
        }, 3600);
    }

    function setComposerStatus(form, message, isError) {
        var status = qs('[data-cf-composer-status]', form);
        if (!status) return;
        status.textContent = message || '';
        status.classList.toggle('is-error', !!isError);
    }

    function resetCommunityComposer(form) {
        var body = qs('[data-feed-textarea]', form);
        var file = qs('[data-feed-file]', form);
        var name = qs('[data-feed-file-name]', form);
        var preview = qs('[data-cf-composer-preview]', form);
        form.reset();
        if (body) {
            body.value = '';
            body.style.height = '';
        }
        if (file) file.value = '';
        if (name) name.textContent = '';
        if (preview) preview.hidden = true;
        showError(qs('[data-feed-error]', form), '');
        setComposerStatus(form, '', false);
        measureComposer();
    }

    function syncComposerPreview(input) {
        var form = input.closest('form');
        var file = input.files && input.files[0];
        var preview = qs('[data-cf-composer-preview]', form);
        var name = qs('[data-feed-file-name]', form);
        if (name) name.textContent = file ? file.name : '';
        if (preview) preview.hidden = !file;
        measureComposer();
    }

    function closePostMenu(element) {
        var menu = element.closest('details');
        if (menu) menu.open = false;
    }

    function submitCommunityComposer(form) {
        if (form.getAttribute('data-busy') === '1') return;
        var body = qs('[data-feed-textarea]', form);
        var file = qs('[data-feed-file]', form);
        var errorBox = qs('[data-feed-error]', form);
        var text = body ? body.value.trim() : '';
        var upload = file && file.files && file.files[0];
        if (!text && !upload) {
            showError(errorBox, 'Write something or attach a file before posting.');
            if (body) body.focus();
            return;
        }
        if (upload && upload.size > MAX_FILE_BYTES) {
            showError(errorBox, 'Attachments must be 25 MB or smaller.');
            return;
        }

        var button = qs('button[type="submit"]', form);
        form.setAttribute('data-busy', '1');
        if (button) button.disabled = true;
        showError(errorBox, '');
        setComposerStatus(form, 'Posting…', false);

        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            var root = form.closest('[data-cf-feed]') || document;
            var list = qs('[data-cf-feed-list]', root);
            if (list && data.html) {
                var empty = qs('[data-feed-empty]', list);
                if (empty) empty.remove();
                list.insertAdjacentHTML('afterbegin', data.html);
            }
            setLatestId(root, data.post_id);
            resetCommunityComposer(form);
            setComposerStatus(form, 'Posted to the community.', false);
            showToast('Your post is now live.');
        }).catch(function (error) {
            showError(errorBox, error.message);
            setComposerStatus(form, '', false);
        }).finally(function () {
            form.removeAttribute('data-busy');
            if (button) button.disabled = false;
        });
    }

    function updateSaveState(post, saved) {
        post.setAttribute('data-cf-saved', saved ? 'true' : 'false');
        qsa('.cf-post-menu-panel [data-cf-save-label]', post).forEach(function (label) {
            label.textContent = saved ? 'Remove from saved' : 'Save post';
        });
        qsa('.cf-post-save [data-cf-save-label]', post).forEach(function (label) {
            label.textContent = saved ? 'Saved' : 'Save';
        });
        qsa('.cf-post-save .cf-post-action', post).forEach(function (button) {
            button.setAttribute('aria-pressed', saved ? 'true' : 'false');
        });
    }

    function submitCommunitySave(form) {
        var post = form.closest('[data-cf-post]');
        if (!post || form.getAttribute('data-busy') === '1') return;
        form.setAttribute('data-busy', '1');
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            updateSaveState(post, !!data.saved);
            closePostMenu(form);
            showToast(data.saved ? 'Post saved.' : 'Removed from saved posts.');
            if (!data.saved && post.closest('[data-cf-saved-view]')) {
                post.classList.add('is-removing');
                window.setTimeout(function () { post.remove(); }, 180);
            }
        }).catch(function () {
            showToast('We could not update that saved post just now.', true);
        }).finally(function () {
            form.removeAttribute('data-busy');
        });
    }

    function submitCommunityDeletePost(form) {
        var message = form.getAttribute('data-confirm') || 'Remove this post?';
        if (!window.confirm(message)) return;
        var post = form.closest('[data-cf-post]');
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function () {
            if (post) {
                post.classList.add('is-removing');
                window.setTimeout(function () { post.remove(); }, 180);
            }
            showToast('Post removed.');
        }).catch(function () {
            showToast('We could not remove that post just now.', true);
        });
    }

    function submitCommunityDeleteComment(form) {
        var message = form.getAttribute('data-confirm') || 'Delete this comment?';
        if (!window.confirm(message)) return;
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            var comment = form.closest('[data-cf-comment-item]');
            var post = form.closest('[data-cf-post]');
            if (comment) comment.remove();
            var count = qs('[data-cf-comment-count]', post || document);
            if (count && data.count != null) count.textContent = String(data.count);
            showToast('Comment deleted.');
        }).catch(function () {
            showToast('We could not delete that comment just now.', true);
        });
    }

    function submitCommunityComment(form) {
        if (form.getAttribute('data-busy') === '1') return;
        var input = qs('[name="body"]', form);
        var post = form.closest('[data-cf-post]');
        var errorBox = qs('[data-cf-comment-error]', post || document);
        var text = input ? input.value.trim() : '';
        if (!text) {
            showError(errorBox, 'Write a comment before sending.');
            if (input) input.focus();
            return;
        }
        var button = qs('button[type="submit"]', form);
        form.setAttribute('data-busy', '1');
        if (button) button.disabled = true;
        showError(errorBox, '');

        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            var parent = form.querySelector('input[name="parent"]');
            var parentId = data.parent_id || (parent ? parent.value : '');
            var target = null;
            if (parentId) target = qs('[data-cf-replies="' + parentId + '"]', post);
            if (!target) target = qs('[data-cf-comments-list]', post);
            if (target && data.html) {
                target.insertAdjacentHTML('beforeend', data.html);
                if (qs('[data-cf-comments-list]', post) === target) {
                    // Newest root comment is at the end; keep the form first.
                }
            }
            if (input) input.value = '';
            var count = qs('[data-cf-comment-count]', post || document);
            if (count && data.count != null) count.textContent = String(data.count);
            if (post) post.classList.add('is-comments-open');
            var toggle = qs('[data-cf-comments-toggle]', post || document);
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
            if (form.matches('[data-cf-reply-form]')) {
                form.hidden = true;
                form.reset();
            } else if (input) {
                input.focus();
            }
            showToast('Comment posted.');
        }).catch(function (error) {
            showError(errorBox, error.message);
        }).finally(function () {
            form.removeAttribute('data-busy');
            if (button) button.disabled = false;
        });
    }

    function openPostEditor(button) {
        var post = button.closest('[data-cf-post]');
        var form = qs('[data-cf-post-edit]', post);
        if (!form) return;
        closePostMenu(button);
        form.hidden = false;
        qsa('textarea, input[type="text"]', form).forEach(function (field) {
            field.dataset.originalValue = field.value;
        });
        var body = qs('textarea[name="body"]', form);
        if (body) {
            body.focus();
            body.setSelectionRange(body.value.length, body.value.length);
        }
    }

    function cancelPostEditor(button) {
        var form = button.closest('[data-cf-post-edit]');
        if (!form) return;
        qsa('textarea, input[type="text"]', form).forEach(function (field) {
            if (field.dataset.originalValue != null) field.value = field.dataset.originalValue;
        });
        showError(qs('[data-cf-edit-error]', form), '');
        form.hidden = true;
    }

    function submitPostEdit(form) {
        if (form.getAttribute('data-busy') === '1') return;
        var post = form.closest('[data-cf-post]');
        var errorBox = qs('[data-cf-edit-error]', form);
        var button = qs('button[type="submit"]', form);
        form.setAttribute('data-busy', '1');
        if (button) button.disabled = true;
        showError(errorBox, '');
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            if (post && data.html) {
                post.insertAdjacentHTML('beforebegin', data.html);
                post.remove();
            }
            showToast(data.message || 'Your post has been updated.');
        }).catch(function (error) {
            showError(errorBox, error.message);
        }).finally(function () {
            form.removeAttribute('data-busy');
            if (button) button.disabled = false;
        });
    }

    function closeReportDialog() {
        var dialog = qs('[data-cf-report-dialog]');
        if (!dialog) return;
        if (typeof dialog.close === 'function') dialog.close();
        else dialog.removeAttribute('open');
    }

    function openReportDialog(button) {
        var dialog = qs('[data-cf-report-dialog]');
        if (!dialog) return;
        var postField = qs('[data-cf-report-post]', dialog);
        var commentField = qs('[data-cf-report-comment]', dialog);
        var errorBox = qs('[data-cf-report-error]', dialog);
        if (postField) postField.value = button.getAttribute('data-post-id') || '';
        if (commentField) commentField.value = button.getAttribute('data-comment-id') || '';
        showError(errorBox, '');
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', 'open');
    }

    function submitReport(form) {
        if (form.getAttribute('data-busy') === '1') return;
        var errorBox = qs('[data-cf-report-error]', form);
        var button = qs('button[type="submit"]', form);
        form.setAttribute('data-busy', '1');
        if (button) button.disabled = true;
        showError(errorBox, '');
        jsonRequest(form.action, {
            method: 'POST',
            body: new FormData(form),
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            closeReportDialog();
            form.reset();
            showToast(data.message || 'Thank you. The church office will review this.');
        }).catch(function (error) {
            showError(errorBox, error.message);
        }).finally(function () {
            form.removeAttribute('data-busy');
            if (button) button.disabled = false;
        });
    }

    function loadMorePosts(button) {
        if (button.getAttribute('data-busy') === '1') return;
        var root = button.closest('[data-cf-feed]');
        var list = root ? qs('[data-cf-feed-list]', root) : null;
        var status = root ? qs('[data-cf-load-status]', root) : null;
        var url = new URL(button.getAttribute('data-url'), window.location.origin);
        var before = button.getAttribute('data-before') || '';
        if (before) url.searchParams.set('before', before);
        url.searchParams.set('scope', button.getAttribute('data-scope') || 'feed');
        button.setAttribute('data-busy', '1');
        button.disabled = true;
        if (status) status.textContent = 'Loading earlier posts…';

        jsonRequest(url.toString(), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (data) {
            if (list && data.html) list.insertAdjacentHTML('beforeend', data.html);
            button.setAttribute('data-before', data.next_before || '');
            button.hidden = !data.has_more;
            if (status) status.textContent = data.has_more ? '' : 'You have reached the beginning.';
        }).catch(function () {
            if (status) status.textContent = 'Could not load earlier posts. Please try again.';
        }).finally(function () {
            button.removeAttribute('data-busy');
            button.disabled = false;
        });
    }

    function openInboxThread() {
        var inbox = qs('[data-cf-inbox]');
        if (!inbox) return;
        inbox.classList.add('is-thread-open');
        document.body.classList.add('cf-thread-open');
        var thread = qs('[data-account-thread]', inbox);
        if (thread) thread.scrollTop = thread.scrollHeight;
        var input = qs('.cf-thread-input', inbox);
        if (input && window.matchMedia('(min-width: 901px)').matches) input.focus();
    }

    function closeInboxThread() {
        var inbox = qs('[data-cf-inbox]');
        if (inbox) inbox.classList.remove('is-thread-open');
        document.body.classList.remove('cf-thread-open');
    }

    function measureComposer() {
        var root = document.documentElement;
        var composer = qs('[data-cf-composer]');
        if (!composer || window.innerWidth > 900) {
            root.style.removeProperty('--cf-composer-space');
            return;
        }
        root.style.setProperty(
            '--cf-composer-space',
            Math.round(composer.getBoundingClientRect().height) + 'px'
        );
    }

    var composerObserver = null;

    function observeComposer() {
        var composer = qs('[data-cf-composer]');
        if (!composer || !window.ResizeObserver) {
            measureComposer();
            return;
        }
        if (composerObserver) composerObserver.disconnect();
        composerObserver = new ResizeObserver(measureComposer);
        composerObserver.observe(composer);
        measureComposer();
    }

    function updateVisualViewport() {
        var root = document.documentElement;
        var viewport = window.visualViewport;
        if (!viewport) return;
        var keyboardOpen = (
            window.innerWidth <= 900 &&
            window.innerHeight - viewport.height > 140
        );
        document.body.classList.toggle(
            'cf-keyboard-open',
            keyboardOpen && !!(qs('[data-cf-composer]') || qs('.cf-inbox.is-thread-open'))
        );
        root.style.setProperty('--cf-vv-height', Math.round(viewport.height) + 'px');
        root.style.setProperty('--cf-vv-top', Math.round(viewport.offsetTop) + 'px');
        if (keyboardOpen) {
            root.style.setProperty(
                '--cf-keyboard-offset',
                Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop)) + 'px'
            );
        } else {
            root.style.removeProperty('--cf-keyboard-offset');
        }
    }

    document.addEventListener('sboi:section-updated', function () {
        observeComposer();
        if (!qs('[data-cf-inbox]')) {
            document.body.classList.remove('cf-thread-open');
        }
        if (!qs('[data-cf-composer]')) {
            document.body.classList.remove('cf-keyboard-open');
        }
    });

    // Delegated so the feed keeps working when the account page swaps its
    // section via AJAX (the profile/overview navigation does exactly that).
    document.addEventListener('input', function (event) {
        if (event.target.matches('[data-feed-textarea]')) {
            autoResize(event.target);
            measureComposer();
        }
    });

    document.addEventListener('change', function (event) {
        if (!event.target.matches('[data-feed-file]')) {
            return;
        }
        var form = event.target.closest('form');
        var file = event.target.files && event.target.files[0];
        var name = qs('[data-feed-file-name]', form);
        if (name) {
            name.textContent = file ? file.name : '';
        }
        syncComposerPreview(event.target);
        if (file && file.size > MAX_FILE_BYTES) {
            showError(
                qs('[data-feed-error]', form),
                'Attachments must be 25 MB or smaller.'
            );
        }
    });

    document.addEventListener('click', function (event) {
        var target = event.target;

        var reactionToggle = target.closest('[data-cf-reaction-toggle]');
        if (reactionToggle) {
            var reactionForm = reactionToggle.closest('[data-feed-reaction]');
            if (reactionForm) {
                if (reactionForm.classList.contains('is-open')) {
                    closeReactionPicker(reactionForm);
                } else {
                    openReactionPicker(reactionForm);
                }
            }
            return;
        }

        var attach = target.closest('[data-cf-attach]');
        if (attach) {
            var attachForm = attach.closest('form');
            var fileInput = attachForm && qs('[data-feed-file]', attachForm);
            if (fileInput) fileInput.click();
            return;
        }

        var clear = target.closest('[data-cf-attach-clear]');
        if (clear) {
            var clearForm = clear.closest('form');
            var clearInput = clearForm && qs('[data-feed-file]', clearForm);
            if (clearInput) {
                clearInput.value = '';
                syncComposerPreview(clearInput);
            }
            return;
        }

        var commentsToggle = target.closest('[data-cf-comments-toggle]');
        if (commentsToggle) {
            var post = commentsToggle.closest('[data-cf-post]');
            if (!post) return;
            var open = post.classList.toggle('is-comments-open');
            commentsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (open) {
                var commentInput = qs('[data-cf-comment] [name="body"]', post);
                if (commentInput) commentInput.focus();
            }
            return;
        }

        var replyButton = target.closest('[data-cf-reply]');
        if (replyButton) {
            var comment = replyButton.closest('[data-cf-comment-item]');
            var replyForm = comment && qs('[data-cf-reply-form]', comment);
            if (replyForm) {
                replyForm.hidden = false;
                var replyInput = qs('[name="body"]', replyForm);
                if (replyInput) replyInput.focus();
            }
            return;
        }

        var replyCancel = target.closest('[data-cf-reply-cancel]');
        if (replyCancel) {
            var cancelForm = replyCancel.closest('[data-cf-reply-form]');
            if (cancelForm) {
                cancelForm.hidden = true;
                cancelForm.reset();
            }
            return;
        }

        var editButton = target.closest('[data-cf-edit]');
        if (editButton) {
            openPostEditor(editButton);
            return;
        }

        var editCancel = target.closest('[data-cf-edit-cancel]');
        if (editCancel) {
            cancelPostEditor(editCancel);
            return;
        }

        var reportButton = target.closest('[data-cf-report]');
        if (reportButton) {
            openReportDialog(reportButton);
            return;
        }

        var reportClose = target.closest('[data-cf-report-close]');
        if (reportClose) {
            closeReportDialog();
            return;
        }

        var openThread = target.closest('[data-cf-open-thread]');
        if (openThread) {
            // Only take over the click when the office thread is actually on
            // this page. While a member conversation is open the office panel
            // is not rendered, so the link must navigate normally instead of
            // silently doing nothing.
            if (qs('[data-account-thread]')) {
                event.preventDefault();
                openInboxThread();
            }
            return;
        }

        var closeThread = target.closest('[data-cf-close-thread]');
        if (closeThread) {
            closeInboxThread();
            return;
        }

        var more = target.closest('[data-cf-load-more]');
        if (more) {
            loadMorePosts(more);
            return;
        }

        var refresh = target.closest('[data-cf-new-posts]');
        if (refresh) {
            window.location.reload();
            return;
        }

        if (!target.closest('[data-feed-reaction]')) {
            qsa('[data-feed-reaction].is-open').forEach(closeReactionPicker);
        }

        if (!target.closest('details')) {
            qsa('details.cf-post-menu[open], details.cf-user[open]').forEach(function (menu) {
                menu.open = false;
            });
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            var openForm = qs('[data-feed-reaction].is-open');
            if (openForm) {
                closeReactionPicker(openForm);
                var openToggle = qs('[data-cf-reaction-toggle]', openForm);
                if (openToggle) {
                    openToggle.focus();
                }
            }
        }
        var textarea = event.target;
        if (!textarea.matches('[data-feed-textarea]')) {
            return;
        }
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            var form = textarea.closest('form');
            if (form) {
                form.requestSubmit();
            }
        }
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (form.matches('[data-cf-composer]')) {
            event.preventDefault();
            submitCommunityComposer(form);
            return;
        }
        if (form.matches('[data-cf-save]')) {
            event.preventDefault();
            submitCommunitySave(form);
            return;
        }
        if (form.matches('[data-cf-delete]')) {
            event.preventDefault();
            submitCommunityDeletePost(form);
            return;
        }
        if (form.matches('[data-cf-comment-delete]')) {
            event.preventDefault();
            submitCommunityDeleteComment(form);
            return;
        }
        if (form.matches('[data-cf-comment]')) {
            event.preventDefault();
            submitCommunityComment(form);
            return;
        }
        if (form.matches('[data-cf-reply-form]')) {
            event.preventDefault();
            submitCommunityComment(form);
            return;
        }
        if (form.matches('[data-cf-post-edit]')) {
            event.preventDefault();
            submitPostEdit(form);
            return;
        }
        if (form.matches('[data-cf-report-form]')) {
            event.preventDefault();
            submitReport(form);
            return;
        }
        if (form.matches('[data-feed-composer]')) {
            event.preventDefault();
            submitComposer(form);
            return;
        }
        if (form.matches('[data-feed-reaction]')) {
            event.preventDefault();
            submitReaction(form, event.submitter);
            return;
        }
        if (form.matches('[data-feed-comment]')) {
            event.preventDefault();
            submitComment(form);
            return;
        }
        if (form.matches('[data-feed-post-delete]')) {
            event.preventDefault();
            removePost(form);
            return;
        }
        if (form.matches('[data-feed-comment-delete]')) {
            event.preventDefault();
            removeComment(form);
        }
    });

    window.setInterval(function () {
        if (document.hidden) {
            return;
        }
        qsa('[data-feed-root]').forEach(function (root) {
            var pollUrl = root.getAttribute('data-feed-poll-url');
            if (!pollUrl) {
                return;
            }
            fetch(pollUrl, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            }).then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.json();
            }).then(function (data) {
                var latest = root.getAttribute('data-feed-latest-id') || '';
                if (!data.latest_id || Number(data.latest_id) <= Number(latest || 0)) {
                    return;
                }
                if (root.hasAttribute('data-cf-feed')) {
                    var newPosts = qs('[data-cf-new-posts]', root);
                    if (newPosts) newPosts.hidden = false;
                    return;
                }
                var composer = qs('[data-feed-textarea]', root);
                var file = qs('[data-feed-file]', root);
                if ((composer && composer.value.trim()) || (file && file.files.length)) {
                    return;
                }
                window.location.reload();
            }).catch(function () {
                /* A later poll will retry. */
            });
        });
    }, POLL_MS);

    window.addEventListener('resize', function () {
        measureComposer();
        updateVisualViewport();
    });

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', updateVisualViewport);
        window.visualViewport.addEventListener('scroll', updateVisualViewport);
    }

    observeComposer();
    updateVisualViewport();
})();
