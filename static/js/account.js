/* Member account: progressive enhancement only.
 *
 * Every form still works with a normal browser POST + redirect. This script
 * adds in-place updates for the two profile modals, the private message
 * thread, mobile drawer toggle, and no-refresh sidebar navigation.
 * There is no framework and no build step.
 */
(function () {
  'use strict';

  var ajaxHeaders = { 'X-Requested-With': 'XMLHttpRequest' };

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
  }

  function closeDrawer() {
    if (!drawerToggle || !drawerOverlay || !accountSidebar) return;
    drawerToggle.setAttribute('aria-expanded', 'false');
    drawerOverlay.classList.remove('is-open');
    accountSidebar.classList.remove('drawer-open');
  }

  if (drawerToggle) {
    drawerToggle.addEventListener('click', function (event) {
      event.preventDefault();
      if (drawerOverlay.classList.contains('is-open')) closeDrawer();
      else openDrawer();
    });
  }

  if (drawerOverlay) {
    drawerOverlay.addEventListener('click', closeDrawer);
  }

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
    if (modal) closeModal(modal);
  });

  /* ---- No-refresh sidebar navigation ------------------------------------ */
  var mainContent = document.querySelector('.account-main');

  function showLoading() {
    if (!mainContent) return;
    mainContent.innerHTML = '<p class="account-empty">Loading…</p>';
  }

  function replaceMainContent(html) {
    if (!mainContent || !html) return;
    var wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    var contentBlock = wrapper.querySelector('[data-account-section]');
    if (contentBlock) {
      mainContent.innerHTML = contentBlock.innerHTML;
    } else {
      mainContent.innerHTML = html;
    }
  }

  document.addEventListener('click', function (event) {
    var link = closest(event.target, '.account-nav-link');
    if (!link) return;
    var href = link.getAttribute('href');
    if (!href || href.startsWith('#')) return;

    event.preventDefault();

    // Close drawer on mobile
    closeDrawer();

    // Update active states
    document.querySelectorAll('.account-nav-link').forEach(function (l) {
      l.classList.remove('active');
    });
    link.classList.add('active');

    showLoading();

    fetch(href, {
      headers: ajaxHeaders,
      credentials: 'same-origin'
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.text();
      })
      .then(function (html) {
        replaceMainContent(html);
        // Re-attach modal listeners for new content
        var modalOpener = document.querySelector('[data-account-open]');
        if (modalOpener && !modalOpener.dataset.listenerAttached) {
          modalOpener.dataset.listenerAttached = '1';
        }
      })
      .catch(function () {
        showFlash('Could not load this section. Please try again.', 'error');
      });
  });

  /* ---- AJAX form helper -------------------------------------------------- */
  function submitForm(form) {
    var targetName = form.getAttribute('data-account-form');
    var target = document.querySelector('[data-account-form-target="' + targetName + '"]');
    var submit = form.querySelector('[type="submit"]');
    if (submit) {
      submit.disabled = true;
      submit.dataset.originalLabel = submit.textContent;
      submit.textContent = 'Saving…';
    }
    return fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: ajaxHeaders,
      credentials: 'same-origin'
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok && data.ok, data: data };
      });
    }).then(function (result) {
      if (!result.ok) {
        if (result.data && result.data.html && target) {
          target.innerHTML = result.data.html;
          focusFirst(target);
        }
        showFlash(result.data && result.data.message ? result.data.message : 'Please check the highlighted fields and try again.', 'error');
        return;
      }

      var modal = closest(form, '.account-modal');
      if (result.data.html) {
        if (targetName === 'profile') {
          var profileCard = document.getElementById('profile');
          if (profileCard) {
            profileCard.outerHTML = result.data.html;
          }
        } else if (targetName === 'membership') {
          var membershipCard = document.getElementById('membership');
          if (membershipCard) {
            membershipCard.outerHTML = result.data.html;
          }
          if (target && result.data.form_html) {
            target.innerHTML = result.data.form_html;
          }
        }
      }
      closeModal(modal);
      showFlash(result.data.message || 'Saved.', 'success');
    }).catch(function () {
      showFlash('We could not save that just now. Please try again.', 'error');
    }).finally(function () {
      if (submit) {
        submit.disabled = false;
        if (submit.dataset.originalLabel) submit.textContent = submit.dataset.originalLabel;
      }
    });
  }

  document.querySelectorAll('form[data-account-form]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      submitForm(form);
    });
  });

  function showFlash(message, kind) {
    var host = document.querySelector('.account-main');
    if (!host) return;
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

  /* ---- Private message thread ------------------------------------------- */
  var thread = document.querySelector('[data-account-thread]');
  var composer = document.querySelector('[data-account-message-form]');
  var sending = false;

  function setStatus(message, isError) {
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
    if (!thread) return 0;
    var value = parseInt(thread.getAttribute('data-after') || '0', 10);
    return isNaN(value) ? 0 : value;
  }

  function appendPayload(items) {
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

  if (composer) {
    composer.addEventListener('submit', function (event) {
      event.preventDefault();
      if (sending) return;
      sending = true;
      var submit = composer.querySelector('[type="submit"]');
      if (submit) {
        submit.disabled = true;
        submit.dataset.originalLabel = submit.textContent;
        submit.textContent = 'Sending…';
      }
      setStatus('', false);
      fetch(composer.action, {
        method: 'POST',
        body: new FormData(composer),
        headers: ajaxHeaders,
        credentials: 'same-origin'
      }).then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok && data.ok, data: data };
        });
      }).then(function (result) {
        if (!result.ok) {
          var message = result.data && result.data.message
            ? result.data.message
            : 'Please check your message and attachment, then try again.';
          setStatus(message, true);
          return;
        }
        composer.reset();
        var fileName = composer.querySelector('[data-account-attachment-name]');
        if (fileName) fileName.textContent = '';
        appendPayload([{ id: result.data.id, html: result.data.html }]);
        setStatus(result.data.message || 'Message sent privately.', false);
      }).catch(function () {
        setStatus('We could not send that message just now. Please try again.', true);
      }).finally(function () {
        sending = false;
        if (submit) {
          submit.disabled = false;
          if (submit.dataset.originalLabel) submit.textContent = submit.dataset.originalLabel;
        }
      });
    });
  }

  var pollUrl = thread && thread.getAttribute('data-poll-url');
  if (pollUrl) {
    window.setInterval(function () {
      if (document.hidden || sending) return;
      fetch(pollUrl + '?after=' + threadAfter() + '&read=1', {
        headers: ajaxHeaders,
        credentials: 'same-origin'
      }).then(function (response) {
        return response.ok ? response.json() : null;
      }).then(function (data) {
        if (data && data.ok) appendPayload(data.messages);
      }).catch(function () {
        /* Offline or sleeping: the next poll catches up. */
      });
    }, 9000);
  }
})();
