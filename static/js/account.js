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
    if (!closest(link, '[data-account-base]')) return;

    var url = new URL(link.href, window.location.origin);
    if (!isAccountUrl(url)) return;

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
    var badge = document.querySelector('[data-account-count="' + name + '"]');
    if (badge) {
      var count = parseInt(value || '0', 10) || 0;
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.hidden = count === 0;
    }
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
      submit.dataset.originalLabel = submit.textContent;
      submit.textContent = label || 'Saving…';
    } else {
      submit.disabled = false;
      if (submit.dataset.originalLabel) submit.textContent = submit.dataset.originalLabel;
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
      fetch(pollUrl + '?after=' + threadAfter() + '&read=1', {
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

  /* ---- Delegated form handling ------------------------------------------ */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || form.nodeName !== 'FORM') return;
    var submitter = event.submitter || form.querySelector('[type="submit"]:focus');
    if (form.matches('[data-account-form]')) {
      event.preventDefault();
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

  /* ---- Initial state ---------------------------------------------------- */
  bindMessagePolling();
  updateNavigation(window.location.href);
  refreshCounts();
})();
