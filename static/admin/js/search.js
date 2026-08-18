(function () {
  'use strict';

  function adminRoot() {
    var forms = document.querySelectorAll('#jazzy-navbar .form-control-navbar');
    if (forms.length) {
      var form = forms[0].closest('form');
      if (form && form.getAttribute('action')) {
        var path = new URL(form.getAttribute('action'), location.href).pathname;
        return path.split('/').slice(0, 2).join('/') + '/';
      }
    }
    return location.pathname.replace(/\/search\/?$/, '/');
  }

  var existing = document.querySelectorAll('#jazzy-navbar .form-control-navbar');
  Array.prototype.forEach.call(existing, function (input) {
    var form = input.closest('form');
    if (form) form.style.display = 'none';
  });

  if (document.querySelector('#jazzy-navbar form[data-sboi-search]')) return;

  var form = document.createElement('form');
  form.className = 'd-flex ms-2';
  form.method = 'get';
  form.action = adminRoot() + 'search/';
  form.setAttribute('data-sboi-search', '');

  var group = document.createElement('div');
  group.className = 'input-group input-group-sm';

  var input = document.createElement('input');
  input.className = 'form-control form-control-navbar';
  input.type = 'search';
  input.name = 'q';
  input.placeholder = 'Search everything...';
  input.setAttribute('aria-label', 'Search everything');

  var btn = document.createElement('button');
  btn.type = 'submit';
  btn.className = 'btn btn-navbar';
  btn.innerHTML = '<i class="fas fa-search"></i>';

  group.appendChild(input);
  group.appendChild(btn);
  form.appendChild(group);

  var msAuto = document.querySelector('#jazzy-navbar .navbar-nav.ms-auto');
  var anchor = existing.length ? existing[0].closest('form') : msAuto;
  var parent = anchor ? anchor.parentNode : document.querySelector('#jazzy-navbar .container-fluid');
  if (parent) parent.insertBefore(form, anchor);
})();