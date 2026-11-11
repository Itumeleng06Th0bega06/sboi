/* Media loader ------------------------------------------------------------
   Site-wide rule: nothing that is still loading may be visible, and a media
   file that fails never shows a broken icon or empty frame.

   Images and videos start hidden (see media-loader.css, enabled by the
   `js-media` class the inline head snippet adds). This script watches every
   image/video on the page, adds `is-media-ready` once the browser has the
   file, and `is-media-broken` (display: none) if it errors.

   It also re-arms when `src` / `srcset` / `poster` changes, so images that
   arrive by AJAX (feed posts, inbox previews, the lightbox) and lazy-loaded
   media follow the same rule.

   Progressive enhancement: without JavaScript the `js-media` class is never
   added and media behaves exactly as before. */
(function () {
  'use strict';

  var READY = 'is-media-ready';
  var BROKEN = 'is-media-broken';
  var ROOT = document.documentElement;
  /* A video that has metadata but never gets a first frame would otherwise
     stay invisible, leaving nothing to click. After this long, a video that
     can at least render its controls is shown. */
  var VIDEO_GRACE_MS = 6000;
  var states = new WeakMap();

  function stateFor(el) {
    var state = states.get(el);
    if (!state) {
      state = { key: '', settled: '', timer: 0 };
      states.set(el, state);
    }
    return state;
  }

  function clearTimer(state) {
    if (state && state.timer) {
      window.clearTimeout(state.timer);
      state.timer = 0;
    }
  }

  function sourceKey(el) {
    var parts = [el.tagName];
    if (el.tagName === 'IMG') {
      parts.push(el.currentSrc || '');
      parts.push(el.getAttribute('src') || '');
      parts.push(el.getAttribute('srcset') || '');
      parts.push(el.getAttribute('sizes') || '');
    } else {
      parts.push(el.getAttribute('src') || '');
      parts.push(el.getAttribute('poster') || '');
      var sources = el.querySelectorAll('source');
      for (var i = 0; i < sources.length; i += 1) {
        parts.push(sources[i].getAttribute('src') || '');
        parts.push(sources[i].getAttribute('srcset') || '');
      }
    }
    return parts.join('\u0001');
  }

  function hasSource(el) {
    if (el.tagName === 'VIDEO') {
      return !!(el.getAttribute('src')
        || el.querySelector('source[src], source[srcset]'));
    }
    return !!(el.getAttribute('src') || el.getAttribute('srcset'));
  }

  function markReady(el) {
    var state = stateFor(el);
    state.settled = 'ready';
    clearTimer(state);
    el.classList.remove(BROKEN);
    el.classList.add(READY);
  }

  function markBroken(el) {
    var state = stateFor(el);
    state.settled = 'broken';
    clearTimer(state);
    el.classList.remove(READY);
    el.classList.add(BROKEN);
  }

  function settle(el, state) {
    if (el.tagName === 'IMG') {
      if (el.complete) {
        if (el.naturalWidth > 0) {
          markReady(el);
        } else if (el.getAttribute('src')) {
          /* Complete with no pixels means the file is gone or corrupt.
             An empty `src` is a placeholder (the lightbox) and simply stays
             hidden until a real source arrives. */
          markBroken(el);
        }
      }
      return;
    }

    if (el.readyState >= 2) {
      markReady(el);
      return;
    }
    if (!state.timer) {
      state.timer = window.setTimeout(function () {
        state.timer = 0;
        if (state.key !== sourceKey(el)) return;
        /* Metadata is enough to show usable controls; without it there is
           nothing worth revealing, so it stays hidden. */
        if (el.readyState >= 1) markReady(el);
      }, VIDEO_GRACE_MS);
    }
  }

  function arm(el) {
    if (!el || (el.tagName !== 'IMG' && el.tagName !== 'VIDEO')) return;
    var state = stateFor(el);
    var key = sourceKey(el);
    if (state.key === key) {
      settle(el, state);
      return;
    }
    state.key = key;
    state.settled = '';
    clearTimer(state);
    el.classList.remove(READY);
    el.classList.remove(BROKEN);
    if (!hasSource(el)) return;
    settle(el, state);
  }

  function scan(node) {
    if (!node || node.nodeType !== 1) return;
    if (node.tagName === 'IMG' || node.tagName === 'VIDEO') arm(node);
    if (!node.querySelectorAll) return;
    var media = node.querySelectorAll('img, video');
    for (var i = 0; i < media.length; i += 1) arm(media[i]);
  }

  function onSuccess(event) {
    var el = event.target;
    if (!el || (el.tagName !== 'IMG' && el.tagName !== 'VIDEO')) return;
    markReady(el);
  }

  function onFailure(event) {
    var el = event.target;
    if (!el || !el.tagName) return;
    if (el.tagName === 'IMG' || el.tagName === 'VIDEO') {
      markBroken(el);
      return;
    }
    /* One failing <source> is not fatal while siblings remain. Chrome does
       not fire `error` on the video itself, so check whether every source
       has now failed (NETWORK_NO_SOURCE). */
    if (el.tagName === 'SOURCE' && el.parentElement
        && el.parentElement.tagName === 'VIDEO') {
      var video = el.parentElement;
      window.setTimeout(function () {
        if (video.networkState === 3) markBroken(video);
      }, 0);
    }
  }

  function onAttribute(target) {
    if (!target || !target.tagName) return;
    if (target.tagName === 'IMG' || target.tagName === 'VIDEO') {
      arm(target);
      return;
    }
    if (target.tagName !== 'SOURCE') return;
    var parent = target.parentElement;
    if (!parent) return;
    if (parent.tagName === 'VIDEO') {
      arm(parent);
    } else if (parent.tagName === 'PICTURE') {
      var img = parent.querySelector('img');
      if (img) arm(img);
    }
  }

  /* Media events do not bubble, but they still reach a capture listener. */
  ['load', 'loadeddata', 'canplay', 'play'].forEach(function (name) {
    document.addEventListener(name, onSuccess, true);
  });
  document.addEventListener('error', onFailure, true);

  if (typeof MutationObserver === 'function') {
    var observer = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i += 1) {
        var record = records[i];
        if (record.type === 'attributes') {
          onAttribute(record.target);
        } else {
          for (var j = 0; j < record.addedNodes.length; j += 1) {
            scan(record.addedNodes[j]);
          }
        }
      }
    });
    observer.observe(ROOT, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['src', 'srcset', 'poster']
    });
  }

  function boot() {
    ROOT.setAttribute('data-media-loader', 'ready');
    ROOT.classList.add('media-loader-ready');
    ROOT.classList.remove('media-timeout');
    scan(ROOT);
    /* Cached media can settle between the scan and the first paint. */
    window.requestAnimationFrame(function () { scan(ROOT); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }

  /* Small public hook for code that swaps a source without an attribute
     mutation (or wants to pick up nodes it just built). */
  window.SBOIMediaLoader = {
    refresh: function () { scan(ROOT); },
    arm: arm
  };
})();
