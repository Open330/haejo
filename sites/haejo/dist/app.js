// Haejo landing: mobile menu and copy button. The page reads fine without it.
(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');

  var button = document.querySelector('.menu-button');
  var nav = document.getElementById('nav');
  if (button && nav) {
    var setOpen = function (open) {
      nav.classList.toggle('open', open);
      button.setAttribute('aria-expanded', String(open));
    };
    button.hidden = false;
    button.addEventListener('click', function () {
      setOpen(button.getAttribute('aria-expanded') !== 'true');
    });
    nav.addEventListener('click', function (event) {
      if (event.target.closest('a')) setOpen(false);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        button.focus();
      }
    });
  }

  var fallbackCopy = function (text) {
    var area = document.createElement('textarea');
    area.className = 'sr-only clipboard-fallback';
    area.value = text;
    area.setAttribute('readonly', '');
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (error) { ok = false; }
    area.remove();
    return ok;
  };
  document.querySelectorAll('[data-copy]').forEach(function (copy) {
    var source = document.getElementById(copy.dataset.copy);
    if (!source) return;
    var label = copy.textContent;
    copy.hidden = false;
    copy.addEventListener('click', function () {
      var text = source.textContent.trim();
      var done = function (ok) {
        if (!ok) return;
        copy.textContent = copy.dataset.done;
        setTimeout(function () { copy.textContent = label; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallbackCopy(text)); });
      } else {
        done(fallbackCopy(text));
      }
    });
  });
})();
