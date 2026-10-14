/* Only authored bindings are translated. Input values, URLs and source/customer data are untouched. */
(function () {
  'use strict';
  const copy = JSON.parse(document.getElementById('public-dictionary').textContent);
  let locale = navigator.language.toLowerCase().startsWith('ru') ? 'ru' : 'en';
  try { const saved = localStorage.getItem('valyqon.shell.locale'); if (['ru', 'en'].includes(saved)) locale = saved; } catch (_) {}
  const explicit = new URLSearchParams(location.search).get('lang');
  if (['ru', 'en'].includes(explicit)) {
    locale = explicit;
    try { localStorage.setItem('valyqon.shell.locale', locale); } catch (_) {}
  }
  const t = value => locale === 'ru' ? (copy[value] || value) : value;
  function url(value) {
    const target = new URL(value, location.origin);
    if (target.origin === location.origin) target.searchParams.set('lang', locale);
    return target.pathname + target.search + target.hash;
  }
  function message(node, key) {
    node.dataset.publicCopy = key;
    if (node.tagName !== 'BUTTON') node.setAttribute('role', 'status');
    node.textContent = t(key);
  }
  function validation(input) {
    input.setCustomValidity('');
    if (input.validity.valid) return;
    const key = input.validity.valueMissing ? 'Please complete this field.' : input.validity.typeMismatch ? 'Enter a valid email address.' : input.validity.tooShort ? 'Use at least 12 characters for your password.' : 'Please check this value.';
    input.setCustomValidity(t(key));
  }
  function bind() {
    document.documentElement.lang = locale;
    document.querySelectorAll('[data-public-copy]').forEach(node => { node.textContent = t(node.dataset.publicCopy); });
    for (const attribute of ['aria-label', 'placeholder']) {
      document.querySelectorAll('[data-public-' + attribute + ']').forEach(node => node.setAttribute(attribute, t(node.getAttribute('data-public-' + attribute))));
    }
    document.querySelectorAll('[data-public-locale]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.publicLocale === locale));
      button.onclick = () => {
        locale = button.dataset.publicLocale;
        try { localStorage.setItem('valyqon.shell.locale', locale); } catch (_) {}
        history.replaceState(null, '', url(location.href));
        bind();
      };
    });
    document.querySelectorAll('a[href]').forEach(link => {
      if (link.getAttribute('href').startsWith('/') && !link.getAttribute('href').startsWith('//')) link.href = url(link.getAttribute('href'));
    });
    const heading = document.querySelector('.form h2') || document.querySelector('main h1, main h2');
    document.title = (document.body.classList.contains('auth-premium') ? heading?.textContent : t(document.body.dataset.publicTitle || 'Global Procurement Intelligence powered by AI')) + ' · VALYQON AI';
    const description = document.querySelector('meta[name="description"]');
    if (description) description.content = t('Global Procurement Intelligence powered by AI');
    document.querySelectorAll('input').forEach(input => {
      input.oninvalid = () => validation(input);
      input.oninput = () => input.setCustomValidity('');
      if (input.validationMessage && input.validity.customError) validation(input);
    });
    const menu = document.getElementById('publicMenu');
    if (menu) menu.onclick = () => {
      const nav = document.getElementById('publicNav');
      const expanded = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(expanded));
      nav.classList.toggle('is-open', expanded);
    };
  }
  window.PublicLocale = {t, bind, message, url, get locale() { return locale; }};
})();
