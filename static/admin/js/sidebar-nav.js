(function () {
    'use strict';

    var MAIN_SELECTOR = 'main.app-main';
    var NAVBAR_SEARCH = 'form.d-flex.ms-2';
    var ADMIN_PREFIX = '/' + (window.location.pathname.split('/')[1] || 'admin');

    function sameOrigin(url) {
        try {
            return new URL(url).origin === window.location.origin;
        } catch (e) {
            return false;
        }
    }

    function isEligibleLink(link, event) {
        if (event.button !== 0) {
            return false;
        }
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return false;
        }
        if (link.target && link.target !== '_self') {
            return false;
        }
        if (link.hasAttribute('download')) {
            return false;
        }
        var href = link.getAttribute('href');
        if (!href || href.charAt(0) === '#') {
            return false;
        }
        var abs = link.href;
        if (!abs || !sameOrigin(abs)) {
            return false;
        }
        var path = abs.replace(window.location.origin, '');
        if (path.indexOf(ADMIN_PREFIX + '/') !== 0) {
            return false;
        }
        if (/\/delete\//.test(path)) {
            return false;
        }
        if (path.indexOf('_popup=') !== -1) {
            return false;
        }
        if (document.body && document.body.classList.contains('popup')) {
            return false;
        }
        return true;
    }

    function isContentScript(src) {
        if (/\/static\/admin\/js\/(sidebar-nav|delete-modal)\.js/.test(src)) {
            return false;
        }
        if (/\/static\/admin\/js\//.test(src)) {
            return true;
        }
        if (/\/static\/jazzmin\/js\/change_list\.js/.test(src)) {
            return true;
        }
        if (/\/static\/jazzmin\/js\/change_form\.js/.test(src)) {
            return true;
        }
        if (/select2\.min\.js/.test(src)) {
            return true;
        }
        return false;
    }

    function scriptSrc(node) {
        var src = node.getAttribute('src');
        if (!src) {
            return null;
        }
        try {
            return new URL(src, node.baseURI || document.baseURI).href;
        } catch (e) {
            return null;
        }
    }

    function headHasScript(src) {
        if (!src) {
            return true;
        }
        return Array.prototype.some.call(document.head.querySelectorAll('script[src]'), function (s) {
            return scriptSrc(s) === src;
        });
    }

    function syncHead(doc) {
        var head = document.head;
        doc.querySelectorAll('link[rel="stylesheet"][href]').forEach(function (css) {
            var href = scriptSrc(css);
            if (!href || head.querySelector('link[href="' + href.replace(/"/g, '\\"') + '"]')) {
                return;
            }
            var l = document.createElement('link');
            l.rel = 'stylesheet';
            l.href = href;
            head.appendChild(l);
        });
        doc.querySelectorAll('script[src]').forEach(function (s) {
            var src = scriptSrc(s);
            if (!src || isContentScript(src) || headHasScript(src)) {
                return;
            }
            var ns = document.createElement('script');
            ns.src = src;
            ns.async = false;
            head.appendChild(ns);
        });
    }

    function reinjectInitializers(doc) {
        var seen = {};
        var pending = [];
        doc.querySelectorAll('head script[src], body > script[src]').forEach(function (s) {
            var src = scriptSrc(s);
            if (!src || !isContentScript(src) || seen[src]) {
                return;
            }
            seen[src] = true;
            pending.push(src);
        });
        pending.forEach(function (src) {
            Array.prototype.filter.call(
                document.querySelectorAll('head script[src], body > script[src]'),
                function (e) {
                    return scriptSrc(e) === src;
                }
            ).forEach(function (old) {
                old.remove();
            });
            var ns = document.createElement('script');
            ns.src = src;
            ns.async = false;
            document.head.appendChild(ns);
        });
    }

    function execContentScripts(root) {
        root.querySelectorAll('script').forEach(function (s) {
            var type = (s.type || '').toLowerCase();
            if (type && type !== 'text/javascript' && type !== 'module') {
                return;
            }
            var clone = document.createElement('script');
            Array.prototype.forEach.call(s.attributes, function (attr) {
                if (attr.name === 'async' || attr.name === 'defer') {
                    return;
                }
                clone.setAttribute(attr.name, attr.value);
            });
            if (s.src) {
                clone.src = s.src;
            } else {
                clone.textContent = s.textContent;
            }
            root.appendChild(clone);
            s.remove();
        });
    }

    function syncBodyTail(doc) {
        var mainEl = doc.querySelector(MAIN_SELECTOR);
        doc.body.querySelectorAll('script').forEach(function (s) {
            var insideMain = mainEl && mainEl.contains(s);
            if (s.src) {
                var src = scriptSrc(s);
                if (!src || insideMain || headHasScript(src)) {
                    return;
                }
                var present = Array.prototype.some.call(document.body.querySelectorAll('script[src]'), function (e) {
                    return scriptSrc(e) === src;
                });
                if (present) {
                    return;
                }
                var ns = document.createElement('script');
                ns.src = src;
                ns.async = false;
                document.body.appendChild(ns);
                return;
            }
            if (insideMain) {
                return;
            }
            var clone = document.createElement('script');
            clone.textContent = s.textContent;
            document.body.appendChild(clone);
        });
    }

    function setActiveLink(pathname) {
        document.querySelectorAll('#jazzy-navigation a[href]').forEach(function (a) {
            var href = a.getAttribute('href');
            if (!href) {
                return;
            }
            var p;
            try {
                p = new URL(href, document.baseURI).pathname.replace(/\/$/, '');
            } catch (e) {
                return;
            }
            var match = p === pathname.replace(/\/$/, '');
            a.classList.toggle('active', match);
            var li = a.closest('li');
            if (li) {
                li.classList.toggle('active', match);
            }
        });
    }

    function jazzifyChangelist() {
        var table = document.querySelector('#changelist .results table');
        if (table && !table.classList.contains('table') && !table.classList.contains('table-striped')) {
            table.classList.add('table', 'table-striped');
        }
    }

    function isLoginDoc(doc) {
        var body = doc.body;
        if (body && body.className.indexOf('login') !== -1) {
            return true;
        }
        return !!(doc.querySelector('#login-form'));
    }

    function applyDoc(doc, url, replace) {
        var main = document.querySelector(MAIN_SELECTOR);
        if (!main) {
            window.location.href = url;
            return false;
        }
        var newMain = doc.querySelector(MAIN_SELECTOR);
        if (!newMain) {
            window.location.href = url;
            return false;
        }
        syncHead(doc);
        main.innerHTML = '';
        while (newMain.firstChild) {
            main.appendChild(newMain.firstChild);
        }
        reinjectInitializers(doc);
        execContentScripts(main);
        syncBodyTail(doc);
        document.title = doc.title || document.title;
        if (replace) {
            history.replaceState({ sboiAdminNav: url }, '', url);
        } else {
            history.pushState({ sboiAdminNav: url }, '', url);
        }
        setActiveLink(new URL(url, window.location.origin).pathname);
        jazzifyChangelist();
        window.scrollTo(0, 0);
        document.dispatchEvent(new CustomEvent('sboi:admin-loaded'));
        document.dispatchEvent(new Event('DOMContentLoaded'));
        return true;
    }

    function load(url, replace) {
        fetch(url, {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            return resp.text();
        }).then(function (html) {
            var doc = new DOMParser().parseFromString(html, 'text/html');
            if (isLoginDoc(doc)) {
                window.location.href = url;
                return;
            }
            applyDoc(doc, url, replace);
        }).catch(function () {
            window.location.href = url;
        });
    }

    function landingFor(submitter, action) {
        var name = submitter && submitter.name ? submitter.name : '';
        var path = action.split('?')[0];
        if (name === '_continue') {
            return action;
        }
        if (name === '_addanother') {
            return path.replace(/\/\d+\/change\/$/, '/add/').replace(/\/add\/[^/]*$/, '/add/');
        }
        if (name === '_saveasnew' || name === '_saveacross') {
            return null;
        }
        return path.replace(/\/\d+\/change\/$/, '/').replace(/\/add\/$/, '/');
    }

    function submitForm(form, event) {
        var abs = form.action;
        if (!abs || !sameOrigin(abs)) {
            return;
        }
        var path = abs.replace(window.location.origin, '');
        if (path.indexOf(ADMIN_PREFIX + '/') !== 0) {
            return;
        }
        var method = (form.method || 'get').toLowerCase();
        if (method === 'get') {
            event.preventDefault();
            var url = abs;
            var data = new FormData(form);
            var params = [];
            data.forEach(function (value, key) {
                if (typeof value === 'string') {
                    params.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
                }
            });
            if (params.length) {
                url += (url.indexOf('?') === -1 ? '?' : '&') + params.join('&');
            }
            load(url, false);
            return;
        }
        event.preventDefault();
        fetch(form.action, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: new FormData(form),
            redirect: 'manual'
        }).then(function (resp) {
            if (resp.type === 'opaqueredirect') {
                var landing = landingFor(event.submitter || document.activeElement, form.action);
                if (landing) {
                    load(landing, false);
                } else {
                    window.location.href = form.action;
                }
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
            var doc = new DOMParser().parseFromString(html, 'text/html');
            if (isLoginDoc(doc)) {
                window.location.href = form.action;
                return;
            }
            applyDoc(doc, form.action, true);
        }).catch(function () {
            window.location.href = form.action;
        });
    }

    function setupNavbarSearch() {
        var form = document.querySelector(NAVBAR_SEARCH);
        if (!form) {
            return;
        }
        form.setAttribute('action', window.location.origin + ADMIN_PREFIX + '/search/');
        var input = form.querySelector('input[name="q"]');
        if (input) {
            input.setAttribute('placeholder', 'Search');
        }
    }

    document.addEventListener('click', function (e) {
        var link = e.target.closest ? e.target.closest('a[href]') : null;
        if (!link || !isEligibleLink(link, e)) {
            return;
        }
        e.preventDefault();
        load(link.href, false);
    });

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || form.tagName !== 'FORM') {
            return;
        }
        if (e.defaultPrevented) {
            return;
        }
        if (form.hasAttribute('target')) {
            return;
        }
        if (document.body && document.body.classList.contains('popup')) {
            return;
        }
        var insideMain = !!(form.closest && form.closest(MAIN_SELECTOR));
        if (!insideMain && !(form.matches && form.matches(NAVBAR_SEARCH))) {
            return;
        }
        submitForm(form, e);
    });

    window.addEventListener('popstate', function (e) {
        var url = e.state && e.state.sboiAdminNav;
        if (url && sameOrigin(url) && url.indexOf(ADMIN_PREFIX + '/') === 0) {
            load(url, true);
        }
    });

    window.sboiNav = {
        load: load
    };

    if (document.body && !document.body.classList.contains('popup') &&
            window.location.pathname.indexOf(ADMIN_PREFIX + '/') === 0) {
        jazzifyChangelist();
    }
    setupNavbarSearch();
})();