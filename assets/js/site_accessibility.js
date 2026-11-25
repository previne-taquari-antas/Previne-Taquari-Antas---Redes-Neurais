/* Shared progressive enhancements for public pages and generated reports. */
(function () {
  'use strict';
  function init() {
    var main = document.querySelector('main, [role="main"]');
    if (main && !document.querySelector('.previne-skip-link')) {
      if (!main.id) {
        var id = 'previne-main';
        while (document.getElementById(id)) id += '-content';
        main.id = id;
      }
      if (!main.hasAttribute('tabindex')) main.tabIndex = -1;
      var skip = document.createElement('a');
      skip.className = 'previne-skip-link';
      skip.href = '#' + main.id;
      skip.textContent = 'Pular para o conteúdo';
      document.body.insertBefore(skip, document.body.firstChild);
    }
    var nav = document.querySelector('.site-nav');
    if (nav) {
      var sizeNav = function () {
        document.documentElement.style.setProperty('--previne-nav-height', nav.getBoundingClientRect().height + 'px');
      };
      sizeNav();
      if (window.ResizeObserver) new ResizeObserver(sizeNav).observe(nav);
      else window.addEventListener('resize', sizeNav);
    }
    function sizeTable(box) {
      var overflowing = box.scrollWidth > box.clientWidth + 1;
      if (overflowing) {
        box.tabIndex = 0;
        box.setAttribute('role', 'region');
        box.setAttribute('aria-label', 'Tabela com rolagem horizontal');
      } else {
        box.removeAttribute('tabindex');
        box.removeAttribute('role');
        box.removeAttribute('aria-label');
      }
    }
    var observer = window.ResizeObserver && new ResizeObserver(function (entries) {
      entries.forEach(function (entry) { sizeTable(entry.target.tagName === 'TABLE' ? entry.target.parentElement : entry.target); });
    });
    function tables() {
      document.querySelectorAll('table').forEach(function (table) {
        if (table.closest('.previne-table-scroll, .leaflet-control, .leaflet-popup')) return;
        var parent = table.parentElement;
        // Preserve existing scroll containers and their layout contracts.
        if (parent !== document.body && /auto|scroll/.test(getComputedStyle(parent).overflowX)) return;
        var box = document.createElement('div');
        box.className = 'previne-table-scroll';
        parent.insertBefore(box, table);
        box.appendChild(table);
        sizeTable(box);
        if (observer) { observer.observe(box); observer.observe(table); }
      });
    }
    tables();
    var pending = false;
    new MutationObserver(function (records) {
      if (pending || !records.some(function (r) { return r.addedNodes.length; })) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; tables(); });
    }).observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
