/* Member account: progressive enhancement only.
 *
 * Every form still works with a normal browser POST + redirect. This script
 * adds in-place updates for the account sections, profile modals, children,
 * settings, notifications and the private message thread. No framework and
 * no build step.
 */
(function () {
  'use strict';

  var ajaxHeaders = { 'X-Requested-With': 'XMLHttpRequest' };
  var shell = document.querySelector('[data-account-base]');
  var accountBase = shell ? new URL(shell.getAttribute('data-account-base'), window.location.origin).pathname : '/members/account/';
  var countsUrl = shell ? shell.getAttribute('data-account-counts-url') : '';
  var siteSuffix = document.title.split(' · ').slice(1).join(' · ');
  var sendingMessage = false;
  var pollTimer = null;

  function closest(element, selector) {
    while (element && element.nodeType === 1) {
      if (element.matches(selector)) return element;
      element = element.parentElement;
    }
    return null;
  }

  function focusFirst(container) {
    var field = container && container.querySelector('input:not([type="hidden"]), textarea, select, button');
    if (field) field.focus();
  }

  function documentSection() {
    return document.querySelector('[data-account-section]');
  }

  /* ---- Spouse name: only when married ----------------------------------- */
  (function () {
    var statusEl = document.querySelector('select[name="marital_status"]');
    if (!statusEl) return;
    function toggle() {
      var spouses = document.querySelectorAll('input[name="spouse_name"], textarea[name="spouse_name"], .account-form-field[data-for-spouse]');
      for (var i = 0; i < spouses.length; i++) {
        var container = spouses[i].closest('.account-form-field');
        if (!container) container = spouses[i].parentElement;
        if (container) container.style.display = statusEl.value === 'married' ? '' : 'none';
      }
      // Fallback: find any field whose label contains "Spouse"
      var fields = document.querySelectorAll('.account-form-field');
      for (var j = 0; j < fields.length; j++) {
        var label = fields[j].querySelector('label');
        if (label && (label.textContent || '').indexOf('Spouse') !== -1) {
          fields[j].style.display = statusEl.value === 'married' ? '' : 'none';
        }
      }
    }
    toggle();
    statusEl.addEventListener('change', toggle);
  })();

  /* ---- Flash messages ---------------------------------------------------- */
  function showFlash(message, kind) {
    var host = document.querySelector('.account-main');
    if (!host || !message) return;
    var flashes = host.querySelector('.account-flashes');
    if (!flashes) {
      flashes = document.createElement('div');
      flashes.className = 'account-flashes';
      flashes.setAttribute('role', 'status');
      flashes.setAttribute('aria-live', 'polite');
      host.insertBefore(flashes, host.firstChild);
    }
    var note = document.createElement('p');
    note.className = 'account-flash account-flash--' + (kind || 'info');
    note.textContent = message;
    flashes.innerHTML = '';
    flashes.appendChild(note);
    window.setTimeout(function () {
      if (note.parentNode) note.parentNode.removeChild(note);
    }, 6500);
  }

  /* ---- Modals ----------------------------------------------------------- */
  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add('account-modal-open');
    focusFirst(modal.querySelector('.account-modal-panel'));
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.hidden = true;
    if (!document.querySelector('.account-modal:not([hidden])')) {
      document.body.classList.remove('account-modal-open');
    }
  }

  /* ---- Mobile drawer ---------------------------------------------------- */
  var drawerToggle = document.querySelector('[data-account-drawer-toggle]');
  var drawerOverlay = document.querySelector('.account-drawer-overlay');
  var accountSidebar = document.querySelector('.account-sidebar');

  function openDrawer() {
    if (!drawerToggle || !drawerOverlay || !accountSidebar) return;
    drawerToggle.setAttribute('aria-expanded', 'true');
    drawerOverlay.classList.add('is-open');
    accountSidebar.classList.add('drawer-open');
    document.body.classList.add('account-drawer-open');
    var closeButton = accountSidebar.querySelector('[data-account-drawer-close]');
    if (closeButton) closeButton.focus();
  }

  function closeDrawer(returnFocus) {
    if (!drawerToggle || !drawerOverlay || !accountSidebar) return;
    var wasOpen = accountSidebar.classList.contains('drawer-open');
    drawerToggle.setAttribute('aria-expanded', 'false');
    drawerOverlay.classList.remove('is-open');
    accountSidebar.classList.remove('drawer-open');
    document.body.classList.remove('account-drawer-open');
    if (returnFocus && wasOpen) drawerToggle.focus();
  }

  if (drawerToggle) {
    drawerToggle.addEventListener('click', function (event) {
      event.preventDefault();
      if (drawerOverlay.classList.contains('is-open')) closeDrawer(true);
      else openDrawer();
    });
  }

  document.querySelectorAll('.account-drawer-overlay, [data-account-drawer-close]').forEach(function (element) {
    element.addEventListener('click', function (event) {
      event.preventDefault();
      closeDrawer(true);
    });
  });

  window.addEventListener('resize', function () {
    if (window.innerWidth > 960) closeDrawer(false);
  });

  document.addEventListener('click', function (event) {
    var opener = closest(event.target, '[data-account-open]');
    if (opener) {
      event.preventDefault();
      openModal(opener.getAttribute('data-account-open'));
      return;
    }
    var closer = closest(event.target, '[data-account-modal-close]');
    if (closer) {
      event.preventDefault();
      closeModal(closest(closer, '.account-modal'));
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    var modal = document.querySelector('.account-modal:not([hidden])');
    if (modal) {
      closeModal(modal);
      return;
    }
    closeDrawer(true);
  });

  /* ---- Section navigation ----------------------------------------------- */
  function setBusy(isBusy) {
    var section = documentSection();
    if (!section) return;
    section.classList.toggle('is-loading', isBusy);
    if (isBusy) section.setAttribute('aria-busy', 'true');
    else section.removeAttribute('aria-busy');
  }

  function updateNavigation(url) {
    var path = new URL(url, window.location.origin).pathname;
    var current = null;
    document.querySelectorAll('.account-nav-link[href]').forEach(function (link) {
      var linkPath = new URL(link.href, window.location.origin).pathname;
      var active = linkPath === path;
      link.classList.toggle('active', active);
      if (active) {
        link.setAttribute('aria-current', 'page');
        current = link;
      } else {
        link.removeAttribute('aria-current');
      }
    });
    var label = document.querySelector('.account-mobile-current');
    if (label && current) {
      var name = current.querySelector('.account-nav-label');
      if (name) label.textContent = name.textContent;
    }
  }

  function updateTitleFromSection() {
    var section = documentSection();
    if (!section) return;
    var title = section.getAttribute('data-account-title');
    if (title) {
      document.title = title + (siteSuffix ? ' · ' + siteSuffix : '');
    }
  }

  function scrollToHash(hash) {
    if (!hash || hash === '#') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    var target = document.getElementById(hash.replace(/^#/, ''));
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function replaceSection(html) {
    var wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    var next = wrapper.querySelector('[data-account-section]');
    var current = documentSection();
    if (!next || !current) return false;
    current.replaceWith(next);
    bindMessagePolling();
    document.dispatchEvent(new CustomEvent('sboi:section-updated'));
    return true;
  }

  function replaceById(id, html) {
    if (!html) return;
    var current = document.getElementById(id);
    if (!current) return;
    var wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    var next = wrapper.firstElementChild;
    if (next) current.replaceWith(next);
  }

  function loadSection(url, options) {
    options = options || {};
    var target = new URL(url, window.location.origin);
    if (target.origin !== window.location.origin) {
      window.location.href = target.href;
      return;
    }

    var currentPath = window.location.pathname;
    if (target.pathname === currentPath) {
      if (options.push) {
        window.history.pushState(
          { account: true, scrollY: window.scrollY },
          '',
          target.pathname + target.search + target.hash
        );
      }
      updateNavigation(target.pathname);
      updateTitleFromSection();
      scrollToHash(target.hash);
      closeDrawer(false);
      return;
    }

    setBusy(true);
    closeDrawer(false);

    fetch(target.href, {
      headers: ajaxHeaders,
      credentials: 'same-origin'
    }).then(function (response) {
      if (response.redirected) {
        window.location.href = response.url;
        throw new Error('Redirected');
      }
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.text();
    }).then(function (html) {
      if (!replaceSection(html)) throw new Error('No account section');
      updateTitleFromSection();
      updateNavigation(target.pathname);
      if (options.push) {
        window.history.pushState(
          { account: true, scrollY: window.scrollY },
          '',
          target.pathname + target.search + target.hash
        );
      }
      if (target.hash) scrollToHash(target.hash);
      else if (options.restoreScroll != null) window.scrollTo(0, options.restoreScroll);
      else window.scrollTo({ top: 0, behavior: 'smooth' });
      var heading = documentSection() && documentSection().querySelector('h1');
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        heading.focus({ preventScroll: true });
      }
      refreshCounts();
    }).catch(function () {
      showFlash('Could not load this section. Please try again.', 'error');
    }).then(function () {
      setBusy(false);
    });
  }

  function isPlainClick(event) {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  }

  function isAccountUrl(url) {
    return url.origin === window.location.origin && url.pathname.indexOf(accountBase) === 0;
  }

  document.addEventListener('click', function (event) {
    if (!isPlainClick(event) || event.defaultPrevented) return;

    var notification = closest(event.target, '[data-account-notification-open]');
    if (notification) {
      event.preventDefault();
      openNotification(notification.href);
      return;
    }

    var link = closest(event.target, 'a[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    if (link.hasAttribute('data-account-ajax') && link.getAttribute('data-account-ajax') === 'off') return;
    if (!closest(link, '[data-account-base]')) return;

    var url = new URL(link.href, window.location.origin);
    if (!isAccountUrl(url)) return;
    if (
      url.pathname === window.location.pathname &&
      url.search !== window.location.search
    ) {
      return;
    }

    event.preventDefault();
    loadSection(url.href, { push: true });
  });

  window.addEventListener('popstate', function (event) {
    if (!(event.state && event.state.account)) return;
    loadSection(window.location.href, {
      push: false,
      restoreScroll: event.state.scrollY
    });
  });

  /* ---- Counts and notification links ------------------------------------ */
  function setCount(name, value) {
    var badges = document.querySelectorAll('[data-account-count="' + name + '"]');
    var count = parseInt(value || '0', 10) || 0;
    badges.forEach(function (badge) {
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.hidden = count === 0;
    });
  }

  function setCounts(data) {
    if (!data) return;
    if (data.unread_messages != null) setCount('messages', data.unread_messages);
    if (data.unread_notifications != null) {
      setCount('notifications', data.unread_notifications);
      var publicBadge = document.querySelector('[data-sboi-public-badge]');
      if (publicBadge) {
        var count = parseInt(data.unread_notifications || '0', 10) || 0;
        publicBadge.textContent = count > 99 ? '99+' : String(count);
        publicBadge.hidden = count === 0;
      }
      document.dispatchEvent(new CustomEvent('sboi:notifications-updated'));
    }
  }

  function refreshCounts() {
    if (!countsUrl) return;
    fetch(countsUrl, {
      headers: ajaxHeaders,
      credentials: 'same-origin'
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(setCounts).catch(function () {
      /* Counts are cosmetic; the next navigation will refresh them. */
    });
  }

  function openNotification(url) {
    fetch(url, {
      headers: ajaxHeaders,
      credentials: 'same-origin'
    }).then(function (response) {
      return response.ok ? response.json() : null;
    }).then(function (data) {
      if (!data || !data.ok) {
        window.location.href = url;
        return;
      }
      setCounts(data);
      var target = new URL(data.url || url, window.location.origin);
      if (isAccountUrl(target)) loadSection(target.href, { push: true });
      else window.location.href = target.href;
    }).catch(function () {
      window.location.href = url;
    });
  }

  /* ---- Forms ------------------------------------------------------------ */
  function setSubmitting(form, isSubmitting, label) {
    var submit = form.querySelector('[type="submit"]');
    if (!submit) return;
    if (isSubmitting) {
      submit.disabled = true;
      submit.dataset.originalHtml = submit.innerHTML;
      if (label) submit.textContent = label;
    } else {
      submit.disabled = false;
      if (submit.dataset.originalHtml) {
        submit.innerHTML = submit.dataset.originalHtml;
        delete submit.dataset.originalHtml;
      }
    }
  }

  function postForm(form, submitter) {
    var body = new FormData(form);
    // FormData(form) omits the button that submitted it. Django views use
    // those names (save_preferences, change_password) to pick the action.
    if (submitter && submitter.name) {
      body.append(submitter.name, submitter.value || '');
    }
    return fetch(form.action, {
      method: 'POST',
      body: body,
      headers: ajaxHeaders,
      credentials: 'same-origin'
    }).then(function (response) {
      if (response.redirected) {
        window.location.href = response.url;
        throw new Error('Redirected');
      }
      var contentType = response.headers.get('content-type') || '';
      if (contentType.indexOf('application/json') === -1) {
        throw new Error('Expected JSON');
      }
      return response.json().then(function (data) {
        return { response: response, data: data };
      });
    });
  }

  function handleRecordForm(form, submitter) {
    var name = form.getAttribute('data-account-form');
    var target = document.querySelector('[data-account-form-target="' + name + '"]');
    var modal = closest(form, '.account-modal');
    setSubmitting(form, true);

    postForm(form, submitter).then(function (result) {
      var data = result.data;
      var ok = result.response.ok && data.ok;
      if (ok) {
        if (data.html && name === 'profile') {
          replaceById('profile', data.html);
          var identityName = document.querySelector('.account-identity-text strong');
          var identityEmail = document.querySelector('.account-identity-text span');
          var greeting = document.querySelector('.account-hero h1');
          if (identityName && data.display_name) identityName.textContent = data.display_name;
          if (identityEmail && data.email) identityEmail.textContent = data.email;
          if (greeting && data.greeting_name) {
            greeting.textContent = 'Welcome back, ' + data.greeting_name;
          }
        }
        if (data.html && name === 'membership') replaceById('membership', data.html);
        if (data.membership_html) replaceById('membership', data.membership_html);
        if (data.form_html && target) target.innerHTML = data.form_html;
        if (name === 'admin-profile') {
          // Update admin avatar in topbar and profile view
          if (data.avatar_url !== undefined) {
            var avatars = document.querySelectorAll('.cf-avatar-img[src], .sboi-avatar, .cf-avatar-link img, .cf-avatar--xl');
            avatars.forEach(function (el) {
              if (el.tagName === 'IMG') {
                el.src = data.avatar_url;
                el.alt = data.display_name || '';
              } else if (el.classList.contains('cf-avatar')) {
                el.textContent = data.initials || '';
              }
            });
          }
        }
        closeModal(modal);
        showFlash(data.message || 'Saved.', 'success');
        if (name === 'membership' && document.querySelector('[data-account-children]')) {
          loadSection(window.location.href, { push: false });
        }
        refreshCounts();
      } else {
        if (data.html && target) {
          target.innerHTML = data.html;
          focusFirst(target);
        }
        showFlash(data.message || 'Please check the highlighted fields and try again.', 'error');
      }
    }).catch(function () {
      showFlash('We could not save that just now. Please try again.', 'error');
    }).then(function () {
      setSubmitting(form, false);
    });
  }

  function handleChildrenForm(form, submitter) {
    var confirmMessage = form.getAttribute('data-account-confirm');
    if (confirmMessage && !window.confirm(confirmMessage)) return;
    setSubmitting(form, true);

    postForm(form, submitter).then(function (result) {
      var data = result.data;
      if (data.html) {
        var host = document.querySelector('[data-account-children]');
        if (host) host.innerHTML = data.html;
      }
      showFlash(
        data.message || (result.response.ok && data.ok ? 'Saved.' : 'Could not update your children list.'),
        result.response.ok && data.ok ? 'success' : 'error'
      );
    }).catch(function () {
      showFlash('We could not update your children list. Please try again.', 'error');
    }).then(function () {
      setSubmitting(form, false);
    });
  }

  function handleSectionForm(form, submitter) {
    setSubmitting(form, true);
    postForm(form, submitter).then(function (result) {
      var data = result.data;
      if (data.html) replaceSection(data.html);
      if (data.unread_messages != null || data.unread_notifications != null) {
        setCounts(data);
      } else {
        refreshCounts();
      }
      showFlash(
        data.message || (result.response.ok && data.ok ? 'Saved.' : 'Please try again.'),
        result.response.ok && data.ok ? 'success' : 'error'
      );
    }).catch(function () {
      showFlash('We could not save that just now. Please try again.', 'error');
    }).then(function () {
      setSubmitting(form, false);
    });
  }

  /* ---- Private message thread ------------------------------------------- */
  function currentThread() {
    return document.querySelector('[data-account-thread]');
  }

  function currentComposer() {
    return document.querySelector('[data-account-message-form]');
  }

  function setStatus(message, isError) {
    var composer = currentComposer();
    var status = composer && composer.querySelector('[data-account-message-status]');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('is-error', !!isError);
    if (message) {
      window.setTimeout(function () {
        if (status.textContent === message) status.textContent = '';
      }, 6000);
    }
  }

  function threadAfter() {
    var thread = currentThread();
    if (!thread) return 0;
    var value = parseInt(thread.getAttribute('data-after') || '0', 10);
    return isNaN(value) ? 0 : value;
  }

  function appendPayload(items) {
    var thread = currentThread();
    if (!thread || !items || !items.length) return;
    var empty = thread.querySelector('[data-account-thread-empty]');
    if (empty) empty.parentNode.removeChild(empty);
    var highest = threadAfter();
    items.forEach(function (item) {
      if (document.getElementById('message-' + item.id)) return;
      var wrapper = document.createElement('div');
      wrapper.innerHTML = item.html;
      var bubble = wrapper.firstElementChild;
      if (!bubble) return;
      thread.appendChild(bubble);
      if (item.id > highest) highest = item.id;
    });
    thread.setAttribute('data-after', String(highest));
    thread.scrollTop = thread.scrollHeight;
  }

  function handleMessageForm(form, submitter) {
    if (sendingMessage) return;
    sendingMessage = true;
    setSubmitting(form, true, 'Sending…');
    setStatus('', false);

    postForm(form, submitter).then(function (result) {
      var data = result.data;
      if (!(result.response.ok && data.ok)) {
        setStatus(data.message || 'Please check your message and attachment, then try again.', true);
        return;
      }
      form.reset();
      var fileName = form.querySelector('[data-account-attachment-name]');
      if (fileName) fileName.textContent = '';
      appendPayload([{ id: data.id, html: data.html }]);
      setStatus(data.message || 'Message sent privately.', false);
    }).catch(function () {
      setStatus('We could not send that message just now. Please try again.', true);
    }).then(function () {
      sendingMessage = false;
      setSubmitting(form, false);
    });
  }

  function bindMessagePolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    var thread = currentThread();
    var pollUrl = thread && thread.getAttribute('data-poll-url');
    if (!pollUrl) return;

    pollTimer = window.setInterval(function () {
      thread = currentThread();
      if (!thread || document.hidden || sendingMessage) return;
      fetch(pollUrl + (pollUrl.indexOf('?') === -1 ? '?' : '&') + 'after=' + threadAfter() + '&read=1', {
        headers: ajaxHeaders,
        credentials: 'same-origin'
      }).then(function (response) {
        return response.ok ? response.json() : null;
      }).then(function (data) {
        if (!data || !data.ok) return;
        appendPayload(data.messages);
        if (data.unread != null) setCount('messages', data.unread);
      }).catch(function () {
        /* Offline or sleeping: the next poll catches up. */
      });
    }, 9000);
  }

  /* ---- Avatar cropper --------------------------------------------------- */
  var AVATAR_OUTPUT_SIZE = 512;

  function avatarOutputType(type) {
    type = (type || '').toLowerCase();
    if (type === 'image/png' || type === 'image/webp') return type;
    return 'image/jpeg';
  }

  function avatarCroppedName(name, type) {
    var base = (name || 'avatar').replace(/\.[^.]+$/, '') || 'avatar';
    var extension = 'jpg';
    if (type === 'image/png') extension = 'png';
    else if (type === 'image/webp') extension = 'webp';
    return base + '-cropped.' + extension;
  }

  function getAvatarState(root) {
    if (!root) return null;
    if (root.__avatarCropper) return root.__avatarCropper;
    var input = root.querySelector('[data-avatar-input]');
    if (!input) return null;
    root.__avatarCropper = {
      root: root,
      input: input,
      stage: root.querySelector('[data-avatar-stage]'),
      imageEl: root.querySelector('[data-avatar-crop-image]'),
      zoomEl: root.querySelector('[data-avatar-zoom]'),
      statusEl: root.querySelector('[data-avatar-status]'),
      filenameEl: root.querySelector('[data-avatar-filename]'),
      previewEl: root.querySelector('[data-avatar-preview]'),
      cropEl: root.querySelector('[data-avatar-crop]'),
      sourceUrl: '',
      previewUrl: '',
      image: null,
      file: null,
      applied: null,
      pending: false,
      naturalW: 0,
      naturalH: 0,
      stageW: 0,
      stageH: 0,
      scale: 1,
      zoom: 1,
      x: 0,
      y: 0,
      drag: null
    };
    return root.__avatarCropper;
  }

  function avatarStatus(state, message, isError) {
    if (!state.statusEl) return;
    state.statusEl.textContent = message || '';
    state.statusEl.classList.toggle('is-error', !!isError);
  }

  function avatarFilename(state, name) {
    if (!state.filenameEl) return;
    state.filenameEl.textContent = name || 'No photo chosen';
    state.filenameEl.title = name || '';
  }

  function replaceAvatarFile(input, file) {
    if (!input || !file || typeof DataTransfer === 'undefined') return false;
    try {
      var transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      return !!(
        input.files &&
        input.files.length === 1 &&
        input.files[0].size === file.size
      );
    } catch (error) {
      return false;
    }
  }

  function restoreAvatarInput(state) {
    if (state.applied && replaceAvatarFile(state.input, state.applied)) {
      avatarFilename(state, state.applied.name);
      return;
    }
    state.input.value = '';
    avatarFilename(state, '');
  }

  function clearAvatarCrop(state) {
    if (state.sourceUrl) {
      URL.revokeObjectURL(state.sourceUrl);
      state.sourceUrl = '';
    }
    state.image = null;
    state.file = null;
    state.pending = false;
    state.drag = null;
    if (state.cropEl) state.cropEl.hidden = true;
    if (state.root) state.root.classList.remove('is-cropping');
    if (state.stage) state.stage.classList.remove('is-dragging');
    if (state.zoomEl) state.zoomEl.value = '100';
    state.zoom = 1;
    if (state.imageEl) {
      state.imageEl.removeAttribute('src');
      state.imageEl.style.width = '';
      state.imageEl.style.height = '';
      state.imageEl.style.transform = '';
    }
  }

  function cancelAvatarCrop(state) {
    clearAvatarCrop(state);
    restoreAvatarInput(state);
    avatarStatus(
      state,
      state.applied
        ? 'Cropped photo ready. Save your profile to update it.'
        : ''
    );
  }

  function updateAvatarPreview(state, file) {
    if (!state.previewEl) return;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(file);
    if (state.previewEl.tagName === 'IMG') {
      state.previewEl.src = state.previewUrl;
      state.previewEl.alt = 'New profile photo preview';
      return;
    }
    var image = document.createElement('img');
    image.className = 'account-avatar-preview-img';
    image.alt = 'New profile photo preview';
    image.setAttribute('data-avatar-preview', '');
    image.src = state.previewUrl;
    state.previewEl.replaceWith(image);
    state.previewEl = image;
  }

  function clampAvatarOffsets(state) {
    var width = state.naturalW * state.scale;
    var height = state.naturalH * state.scale;
    state.x = Math.min(0, Math.max(state.stageW - width, state.x));
    state.y = Math.min(0, Math.max(state.stageH - height, state.y));
  }

  function drawAvatarStage(state) {
    if (!state.imageEl) return;
    state.imageEl.style.width = state.naturalW * state.scale + 'px';
    state.imageEl.style.height = state.naturalH * state.scale + 'px';
    state.imageEl.style.transform =
      'translate3d(' + state.x + 'px, ' + state.y + 'px, 0)';
  }

  function layoutAvatarStage(state, keepCenter) {
    if (!state.stage || !state.naturalW) return;
    var width = state.stage.clientWidth;
    var height = state.stage.clientHeight;
    if (!width || !height) return;
    var previousScale = state.scale;
    var base = Math.max(width / state.naturalW, height / state.naturalH);
    var scale = base * state.zoom;
    if (keepCenter && previousScale) {
      var centerX = (width / 2 - state.x) / previousScale;
      var centerY = (height / 2 - state.y) / previousScale;
      state.x = width / 2 - centerX * scale;
      state.y = height / 2 - centerY * scale;
    } else {
      state.x = (width - state.naturalW * scale) / 2;
      state.y = (height - state.naturalH * scale) / 2;
    }
    state.stageW = width;
    state.stageH = height;
    state.scale = scale;
    clampAvatarOffsets(state);
    drawAvatarStage(state);
  }

  function loadAvatarFile(input) {
    var state = getAvatarState(closest(input, '[data-avatar-cropper]'));
    if (!state) return;
    var file = input.files && input.files[0];
    clearAvatarCrop(state);
    if (!file) {
      restoreAvatarInput(state);
      avatarStatus(state, '');
      return;
    }
    if (!/^image\//i.test(file.type)) {
      restoreAvatarInput(state);
      avatarStatus(state, 'Please choose a JPG, PNG or WebP image.', true);
      return;
    }

    var url = URL.createObjectURL(file);
    state.sourceUrl = url;
    state.file = file;
    avatarStatus(state, 'Loading photo…');

    var image = new Image();
    image.onload = function () {
      if (state.sourceUrl !== url) return;
      state.image = image;
      state.naturalW = image.naturalWidth || image.width;
      state.naturalH = image.naturalHeight || image.height;
      if (!state.naturalW || !state.naturalH) {
        cancelAvatarCrop(state);
        avatarStatus(state, 'That image could not be read. Please try another.', true);
        return;
      }
      state.pending = true;
      state.zoom = 1;
      if (state.zoomEl) state.zoomEl.value = '100';
      if (state.cropEl) state.cropEl.hidden = false;
      if (state.imageEl) state.imageEl.src = url;
      if (state.root) state.root.classList.add('is-cropping');
      avatarFilename(state, file.name);
      avatarStatus(state, 'Drag the photo to frame it, then press Crop & use.');
      window.requestAnimationFrame(function () {
        if (state.pending) layoutAvatarStage(state, false);
      });
    };
    image.onerror = function () {
      if (state.sourceUrl !== url) return;
      clearAvatarCrop(state);
      restoreAvatarInput(state);
      avatarStatus(state, 'That image could not be read. Please try another.', true);
    };
    image.src = url;
  }

  function zoomAvatarCrop(state) {
    if (!state.pending || !state.zoomEl) return;
    var value = parseInt(state.zoomEl.value, 10);
    if (isNaN(value)) value = 100;
    state.zoom = Math.min(300, Math.max(100, value)) / 100;
    layoutAvatarStage(state, true);
  }

  function startAvatarDrag(state, event) {
    if (!state.pending) return;
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault();
    if (state.stage.focus) state.stage.focus({ preventScroll: true });
    state.drag = {
      id: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      x: state.x,
      y: state.y
    };
    state.stage.classList.add('is-dragging');
    if (state.stage.setPointerCapture) {
      try {
        state.stage.setPointerCapture(event.pointerId);
      } catch (error) {
        /* Pointer capture is an enhancement; dragging still works. */
      }
    }
  }

  function moveAvatarDrag(state, event) {
    var drag = state.drag;
    if (!drag || drag.id !== event.pointerId) return;
    state.x = drag.x + event.clientX - drag.startX;
    state.y = drag.y + event.clientY - drag.startY;
    clampAvatarOffsets(state);
    drawAvatarStage(state);
  }

  function endAvatarDrag(state, event) {
    var drag = state.drag;
    if (!drag || drag.id !== event.pointerId) return;
    state.drag = null;
    state.stage.classList.remove('is-dragging');
    if (state.stage.hasPointerCapture && state.stage.hasPointerCapture(event.pointerId)) {
      try {
        state.stage.releasePointerCapture(event.pointerId);
      } catch (error) {
        /* Nothing to release. */
      }
    }
  }

  function avatarDataUrlToBlob(url) {
    try {
      var parts = url.split(',');
      var mime = (parts[0].match(/:(.*?);/) || [])[1] || 'image/jpeg';
      var binary = window.atob(parts[1]);
      var bytes = new Uint8Array(binary.length);
      for (var index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return new Blob([bytes], { type: mime });
    } catch (error) {
      return null;
    }
  }

  function applyAvatarCrop(state) {
    return new Promise(function (resolve) {
      if (!state.pending || !state.image || !state.stageW) {
        resolve(null);
        return;
      }

      var sourceSize = Math.min(
        state.stageW / state.scale,
        state.naturalW,
        state.naturalH
      );
      var sourceX = -state.x / state.scale;
      var sourceY = -state.y / state.scale;
      sourceX = Math.min(Math.max(0, sourceX), state.naturalW - sourceSize);
      sourceY = Math.min(Math.max(0, sourceY), state.naturalH - sourceSize);

      var canvas = document.createElement('canvas');
      canvas.width = AVATAR_OUTPUT_SIZE;
      canvas.height = AVATAR_OUTPUT_SIZE;
      var context = canvas.getContext('2d');
      if (!context) {
        avatarStatus(state, 'We could not crop this photo. Please try another.', true);
        resolve(null);
        return;
      }
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      try {
        context.drawImage(
          state.image,
          sourceX,
          sourceY,
          sourceSize,
          sourceSize,
          0,
          0,
          AVATAR_OUTPUT_SIZE,
          AVATAR_OUTPUT_SIZE
        );
      } catch (error) {
        avatarStatus(state, 'We could not crop this photo. Please try another.', true);
        resolve(null);
        return;
      }

      var requestedType = avatarOutputType(state.file && state.file.type);
      var finish = function (blob) {
        if (!blob) {
          avatarStatus(state, 'We could not prepare the photo. Please try again.', true);
          resolve(null);
          return;
        }
        var type = (blob.type || requestedType).toLowerCase();
        var file;
        try {
          file = new File(
            [blob],
            avatarCroppedName(state.file && state.file.name, type),
            { type: type, lastModified: Date.now() }
          );
        } catch (error) {
          file = blob;
        }
        if (!replaceAvatarFile(state.input, file)) {
          avatarStatus(
            state,
            'This browser cannot crop before upload. The full photo will still be saved.',
            true
          );
          resolve(null);
          return;
        }
        state.pending = false;
        state.applied = file;
        if (state.cropEl) state.cropEl.hidden = true;
        if (state.root) state.root.classList.remove('is-cropping');
        if (state.sourceUrl) {
          URL.revokeObjectURL(state.sourceUrl);
          state.sourceUrl = '';
        }
        updateAvatarPreview(state, file);
        avatarFilename(state, file.name);
        avatarStatus(state, 'Cropped photo ready. Save your profile to update it.');
        resolve(file);
      };

      if (canvas.toBlob) {
        canvas.toBlob(
          finish,
          requestedType,
          requestedType === 'image/jpeg' ? 0.9 : undefined
        );
      } else {
        finish(avatarDataUrlToBlob(canvas.toDataURL(requestedType, 0.9)));
      }
    });
  }

  function pendingAvatarCrop(form) {
    var root = form.querySelector('[data-avatar-cropper]');
    var state = getAvatarState(root);
    return state && state.pending ? state : null;
  }

  document.addEventListener('change', function (event) {
    if (!event.target.matches('[data-avatar-input]')) return;
    loadAvatarFile(event.target);
  });

  document.addEventListener('input', function (event) {
    if (!event.target.matches('[data-avatar-zoom]')) return;
    var state = getAvatarState(closest(event.target, '[data-avatar-cropper]'));
    if (state) zoomAvatarCrop(state);
  });

  document.addEventListener('click', function (event) {
    var state;
    if (closest(event.target, '[data-avatar-apply]')) {
      event.preventDefault();
      state = getAvatarState(closest(event.target, '[data-avatar-cropper]'));
      if (state) applyAvatarCrop(state);
      return;
    }
    if (closest(event.target, '[data-avatar-cancel]')) {
      event.preventDefault();
      state = getAvatarState(closest(event.target, '[data-avatar-cropper]'));
      if (state) cancelAvatarCrop(state);
    }
  });

  document.addEventListener('pointerdown', function (event) {
    var stage = closest(event.target, '[data-avatar-stage]');
    if (!stage) return;
    var state = getAvatarState(closest(stage, '[data-avatar-cropper]'));
    if (state) startAvatarDrag(state, event);
  });

  document.addEventListener('pointermove', function (event) {
    var stage = closest(event.target, '[data-avatar-stage]');
    if (!stage) return;
    var state = getAvatarState(closest(stage, '[data-avatar-cropper]'));
    if (state) moveAvatarDrag(state, event);
  });

  document.addEventListener('pointerup', function (event) {
    var stage = closest(event.target, '[data-avatar-stage]');
    if (!stage) return;
    var state = getAvatarState(closest(stage, '[data-avatar-cropper]'));
    if (state) endAvatarDrag(state, event);
  });

  document.addEventListener('pointercancel', function (event) {
    var stage = closest(event.target, '[data-avatar-stage]');
    if (!stage) return;
    var state = getAvatarState(closest(stage, '[data-avatar-cropper]'));
    if (state) endAvatarDrag(state, event);
  });

  document.addEventListener('keydown', function (event) {
    var stage = closest(event.target, '[data-avatar-stage]');
    if (!stage) return;
    var state = getAvatarState(closest(stage, '[data-avatar-cropper]'));
    if (!state || !state.pending) return;
    var step = event.shiftKey ? 2 : 12;
    var moved = true;
    if (event.key === 'ArrowLeft') state.x += step;
    else if (event.key === 'ArrowRight') state.x -= step;
    else if (event.key === 'ArrowUp') state.y += step;
    else if (event.key === 'ArrowDown') state.y -= step;
    else moved = false;
    if (!moved) return;
    event.preventDefault();
    clampAvatarOffsets(state);
    drawAvatarStage(state);
  });

  window.addEventListener('resize', function () {
    document.querySelectorAll('[data-avatar-cropper]').forEach(function (root) {
      var state = getAvatarState(root);
      if (state && state.pending) layoutAvatarStage(state, true);
    });
  });

  /* ---- Delegated form handling ------------------------------------------ */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || form.nodeName !== 'FORM') return;
    var submitter = event.submitter || form.querySelector('[type="submit"]:focus');
    if (form.matches('[data-account-form]')) {
      event.preventDefault();
      var avatarCrop = pendingAvatarCrop(form);
      if (avatarCrop) {
        var saveButton = form.querySelector('[type="submit"]');
        if (saveButton) saveButton.disabled = true;
        avatarStatus(avatarCrop, 'Preparing your cropped photo…');
        applyAvatarCrop(avatarCrop).then(function () {
          if (saveButton && saveButton.isConnected) saveButton.disabled = false;
          if (form.isConnected) handleRecordForm(form, submitter);
        });
        return;
      }
      handleRecordForm(form, submitter);
    } else if (form.matches('[data-account-child-form]')) {
      event.preventDefault();
      handleChildrenForm(form, submitter);
    } else if (form.matches('[data-account-section-form]')) {
      event.preventDefault();
      handleSectionForm(form, submitter);
    } else if (form.matches('[data-account-message-form]')) {
      event.preventDefault();
      handleMessageForm(form, submitter);
    }
  });

  document.addEventListener('change', function (event) {
    if (!event.target.matches('[data-account-message-form] input[type="file"]')) return;
    var form = closest(event.target, '[data-account-message-form]');
    var name = form && form.querySelector('[data-account-attachment-name]');
    if (name) {
      name.textContent = event.target.files && event.target.files[0]
        ? event.target.files[0].name
        : '';
    }
  });

  document.addEventListener('input', function (event) {
    if (!event.target.matches('.cf-thread-input, .cf-comment-input textarea')) return;
    event.target.style.height = 'auto';
    event.target.style.height = Math.min(event.target.scrollHeight, 110) + 'px';
  });

  document.addEventListener('keydown', function (event) {
    if (!event.target.matches('.cf-thread-input')) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      var form = closest(event.target, '[data-account-message-form]');
      if (form) form.requestSubmit();
    }
  });

  /* ---- Initial state ---------------------------------------------------- */
  bindMessagePolling();
  updateNavigation(window.location.href);
  refreshCounts();
})();
