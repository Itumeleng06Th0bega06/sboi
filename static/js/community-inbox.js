/*
  Member-to-member inbox.

  The inbox still works without JavaScript: every form posts and redirects.
  With JavaScript the selected conversation is refreshed in place, new bubbles
  are appended without reloading the page, and the phone thread view opens on
  top of the conversation list.
*/
(function () {
  'use strict';

  var pollTimer = null;
  var sending = false;

  function qs(selector, scope) {
    return (scope || document).querySelector(selector);
  }

  function dmThread() {
    return qs('[data-cf-dm-thread]');
  }

  function threadAfter(thread) {
    var value = parseInt(thread.getAttribute('data-after') || '0', 10);
    return isNaN(value) ? 0 : value;
  }

  function setStatus(message, isError) {
    var status = qs('[data-cf-dm-status]');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('is-error', !!isError);
    if (message) {
      window.setTimeout(function () {
        if (status.textContent === message) status.textContent = '';
      }, 6000);
    }
  }

  function appendBubbles(items) {
    var thread = dmThread();
    if (!thread || !items || !items.length) return;
    var empty = qs('[data-cf-dm-empty]', thread);
    if (empty) empty.remove();
    var highest = threadAfter(thread);
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

  function send(form) {
    if (sending) return;
    sending = true;
    var button = qs('button[type="submit"]', form);
    if (button) button.disabled = true;
    setStatus('Sending…', false);

    fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (response) {
      return response.json().then(function (data) {
        return { response: response, data: data };
      });
    }).then(function (result) {
      if (!(result.response.ok && result.data.ok)) {
        setStatus(
          result.data.message || 'Please check your message and try again.',
          true
        );
        return;
      }
      form.reset();
      var input = qs('[data-cf-dm-input]', form);
      if (input) input.style.height = '';
      appendBubbles([{ id: result.data.id, html: result.data.html }]);
      setStatus(result.data.message || 'Message sent.', false);
    }).catch(function () {
      setStatus('We could not send that message just now. Please try again.', true);
    }).then(function () {
      sending = false;
      if (button) button.disabled = false;
    });
  }

  function bindPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    var thread = dmThread();
    if (!thread) return;
    var url = thread.getAttribute('data-poll-url');
    if (!url) return;

    pollTimer = window.setInterval(function () {
      thread = dmThread();
      if (!thread || document.hidden || sending) return;
      var target = new URL(url, window.location.origin);
      target.searchParams.set('after', String(threadAfter(thread)));
      target.searchParams.set('read', '1');
      fetch(target.toString(), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).then(function (response) {
        return response.ok ? response.json() : null;
      }).then(function (data) {
        if (!data || !data.ok) return;
        appendBubbles(data.messages);
      }).catch(function () {
        /* Offline or sleeping: the next poll catches up. */
      });
    }, 9000);
  }

  function scrollThread() {
    var thread = dmThread();
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || !form.matches('[data-cf-dm-form]')) return;
    event.preventDefault();
    send(form);
  });

  document.addEventListener('input', function (event) {
    if (!event.target.matches('[data-cf-dm-input]')) return;
    event.target.style.height = 'auto';
    event.target.style.height =
      Math.min(event.target.scrollHeight, 110) + 'px';
  });

  document.addEventListener('keydown', function (event) {
    if (!event.target.matches('[data-cf-dm-input]')) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      var form = event.target.closest('[data-cf-dm-form]');
      if (form) form.requestSubmit();
    }
  });

  document.addEventListener('sboi:section-updated', function () {
    scrollThread();
    bindPolling();
  });

  scrollThread();
  bindPolling();
})();
