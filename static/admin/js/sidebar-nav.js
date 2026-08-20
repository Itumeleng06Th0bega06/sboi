(function () {
    'use strict';

    var MAIN_SELECTOR = 'main.app-main';
    var NAV_SELECTOR = '#jazzy-navigation a[href]';

    var REINIT_SCRIPTS = [
        'admin/js/filters.js',
        'admin/js/inlines.js',
        'admin/js/change_form.js',
        'admin/js/autocomplete.js',
        'static/jazzmin/js/change_list.js',
        'static/vendor/select2/js/select2.min.js'
    ];

    function sameOrigin(url) {
        try {
            return new URL(url).origin === window.location.origin;
        } catch (e) {
            return false;
        }
    }

    function isEligible(link, event) {
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
        if (path.indexOf('/admin/') !== 0) {
            return false;
        }
        if (/\/delete\//.test(path)) {
            return false;
        }
        if (document.body && document.body.classList.contains('popup')) {
            return false;
        }
        return true;
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
            if (!src || headHasScript(src)) {
                return;
            }
            var ns = document.createElement('script');
            ns.src = src;
            ns.async = false;
            head.appendChild(ns);
        });
    }

    function reinjectInitializers() {
        REINIT_SCRIPTS.forEach(function (path) {
            var src = new URL(path, window.location.origin).href;
            var current = Array.prototype.filter.call(document.head.querySelectorAll('script[src]'), function (s) {
                return scriptSrc(s) === src;
            });
            current.forEach(function (old) {
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
            var clone = document.createElement('script');
            if (s.src) {
                clone.src = s.src;
                clone.async = false;
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

    function load(url, replace) {
        var main = document.querySelector(MAIN_SELECTOR);
        if (!main) {
            window.location.href = url;
            return;
        }
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
            var newMain = doc.querySelector(MAIN_SELECTOR);
            if (!newMain) {
                throw new Error('no content');
            }
            if ((doc.querySelector('#login-form') && !doc.querySelector('#changelist-form') && !doc.querySelector('.module form')) || (doc.querySelector('body') && doc.querySelector('body').className.indexOf('login') !== -1)) {
                window.location.href = url;
                return;
            }
            syncHead(doc);
            main.innerHTML = '';
            while (newMain.firstChild) {
                main.appendChild(newMain.firstChild);
            }
            execContentScripts(main);
            syncBodyTail(doc);
            reinjectInitializers();
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
        }).catch(function () {
            window.location.href = url;
        });
    }

    document.addEventListener('click', function (e) {
        var link = e.target.closest ? e.target.closest(NAV_SELECTOR) : null;
        if (!link || !isEligible(link, e)) {
            return;
        }
        e.preventDefault();
        load(link.href, false);
    });

    window.addEventListener('popstate', function (e) {
        var url = e.state && e.state.sboiAdminNav;
        if (url && sameOrigin(url) && url.indexOf('/admin/') !== -1) {
            load(url, true);
        }
    });

    if (document.body && !document.body.classList.contains('popup') &&
            window.location.pathname.indexOf('/admin/') === 0) {
        jazzifyChangelist();
    }
})();
