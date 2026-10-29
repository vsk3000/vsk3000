(() => {
  'use strict';
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const sections = $$('.guide-section');
  const menu = $('.menu-toggle');
  const sidebar = $('#sidebar');
  const toast = $('.toast');
  let toastTimer;
  function notify(message) { toast.textContent = message; toast.classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('visible'), 2500); }
  function closeMenu() { sidebar.classList.remove('is-open'); document.body.classList.remove('menu-open'); menu.setAttribute('aria-expanded', 'false'); }
  menu.addEventListener('click', () => { const open = sidebar.classList.toggle('is-open'); document.body.classList.toggle('menu-open', open); menu.setAttribute('aria-expanded', String(open)); });
  $$('a[href^="#"]').forEach(link => link.addEventListener('click', closeMenu));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
  const mobile = matchMedia('(max-width:760px)');
  mobile.addEventListener('change', () => { if (!mobile.matches) closeMenu(); });
  const toc = $('#section-toc');
  let current = '';
  function setCurrent(section) {
    const id = section.dataset.section;
    if (current === id) return;
    current = id;
    $$('.sidebar a').forEach(link => { if (link.hash === '#' + id) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current'); });
    toc.replaceChildren();
    const headings = $$('h3', section);
    const items = headings.length ? headings : [ $('h1,h2', section) ];
    items.forEach(heading => { const a = document.createElement('a'); a.href = '#' + heading.id; a.textContent = heading.textContent; toc.append(a); });
  }
  function updateScroll() {
    const top = window.scrollY;
    let selected = sections[0];
    for (const section of sections) { if (section.getBoundingClientRect().top <= 150) selected = section; }
    setCurrent(selected);
    const total = document.documentElement.scrollHeight - innerHeight;
    $('.reading-progress span').style.transform = 'scaleX(' + (total > 0 ? Math.min(top / total, 1) : 1) + ')';
    $('.back-to-top').hidden = top < 600;
  }
  let pending = false;
  addEventListener('scroll', () => { if (!pending) { pending = true; requestAnimationFrame(() => { updateScroll(); pending = false; }); } }, { passive: true });
  addEventListener('resize', updateScroll);
  addEventListener('load', updateScroll);
  updateScroll();
  $('.back-to-top').addEventListener('click', () => { location.hash = 'start'; });
  $('.print-button').addEventListener('click', () => print());
  $$('.copy-button').forEach(button => button.addEventListener('click', async () => {
    const code = $('code', button.closest('.code-block'));
    try { await navigator.clipboard.writeText(code.textContent); notify('Команда скопирована'); button.textContent = 'Скопировано ✓'; setTimeout(() => { button.textContent = 'Копировать'; }, 2500); }
    catch { const range = document.createRange(); range.selectNodeContents(code); const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range); notify('Команда выделена — скопируйте её вручную'); }
  }));
  const searchDialog = $('.search-dialog');
  const input = $('#guide-search');
  const results = $('.search-results');
  const searchData = sections.map(section => ({ id: section.dataset.section, title: $('h1,h2', section).textContent, text: section.textContent.replace(/\s+/g, ' ').trim() }));
  function openSearch() { closeMenu(); searchDialog.showModal(); input.focus(); }
  $('.search-trigger').addEventListener('click', openSearch);
  $('.dialog-close').addEventListener('click', () => searchDialog.close());
  document.addEventListener('keydown', event => { if (event.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !$('.image-dialog').open) { event.preventDefault(); if (!searchDialog.open) openSearch(); } });
  input.addEventListener('input', () => {
    const query = input.value.trim().toLocaleLowerCase('ru');
    results.replaceChildren();
    if (!query) { $('.search-status').textContent = 'Введите слово или название раздела.'; return; }
    const found = searchData.filter(item => item.text.toLocaleLowerCase('ru').includes(query));
    $('.search-status').textContent = found.length ? 'Найдено разделов: ' + found.length : 'Ничего не найдено. Попробуйте другое слово.';
    found.forEach(item => {
      const link = document.createElement('a'); link.href = '#' + item.id;
      const title = document.createElement('strong'); title.textContent = item.title;
      const snippet = document.createElement('small'); const position = item.text.toLocaleLowerCase('ru').indexOf(query); const begin = Math.max(0, position - 45); snippet.textContent = (begin ? '…' : '') + item.text.slice(begin, position + query.length + 100) + '…';
      link.append(title, snippet); link.addEventListener('click', () => searchDialog.close()); results.append(link);
    });
  });
  const imageDialog = $('.image-dialog');
  $$('.screenshot').forEach(link => link.addEventListener('click', event => {
    event.preventDefault(); const original = $('img', link); const expanded = $('img', imageDialog); expanded.src = original.src; expanded.alt = original.alt; $('.image-description').textContent = original.alt; imageDialog.showModal();
  }));
  $('.image-close').addEventListener('click', () => imageDialog.close());
  [searchDialog, imageDialog].forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } }));
})();
