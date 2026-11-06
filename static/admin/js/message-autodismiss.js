/**
 * Auto-dismiss Django success messages after 3 seconds.
 * Only targets `li.success` inside `ul.messagelist` in the admin.
 * Errors/warnings stay until manually closed.
 */
(function () {
  'use strict';

  function dismiss(message) {
    message.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
    message.style.opacity = '0';
    message.style.transform = 'translateY(-4px)';
    window.setTimeout(function () {
      if (message.parentNode) {
        message.parentNode.removeChild(message);
      }
      var list = document.querySelector('ul.messagelist');
      if (list && !list.children.length) {
        list.style.display = 'none';
      }
    }, 380);
  }

  function init() {
    var items = document.querySelectorAll('ul.messagelist li.success');
    items.forEach(function (item) {
      window.setTimeout(function () {
        dismiss(item);
      }, 3000);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
