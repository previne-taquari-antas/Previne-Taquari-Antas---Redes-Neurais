/* Seletor de cidade do mapa de previsão. Coordenadas das estações já publicadas. */
(function () {
  'use strict';

  const cities = [
    {id: 'santa_tereza', name: 'Santa Tereza', lat: -29.1781, lon: -51.7322},
    {id: 'mucum', name: 'Muçum', lat: -29.1672, lon: -51.8686}
  ];

  function init(options) {
    const map = options.map;
    const selected = cities.find(city => city.id === options.city);
    if (!map || !selected || typeof L === 'undefined') return;

    const suffix = options.variant === 'usuario' ? '_usuario' : '';
    const cityHref = city => city.id + '_previsao_inundacao' + suffix + '.html';
    let viewMode = 'both', controlledMove = false, resizeTimer = null;
    const fit = (bounds, padding) => {
      controlledMove = true;
      try { map.fitBounds(bounds, {...padding, animate:false}); }
      finally { controlledMove = false; }
    };
    const showCity = () => { viewMode = 'selected'; fit(options.bounds, {padding: [28, 28]}); };
    const showBoth = () => {
      viewMode = 'both';
      const horizontal = Math.min(85, Math.round(map.getSize().x * .23));
      fit(L.latLngBounds(cities.map(city => [city.lat, city.lon])),
        {paddingTopLeft:[horizontal,95],paddingBottomRight:[horizontal,95],maxZoom:12});
    };
    map.on('movestart zoomstart', () => { if (!controlledMove) viewMode = 'manual'; });
    const resize = () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        map.invalidateSize({pan:false});
        if (viewMode === 'both') showBoth();
        else if (viewMode === 'selected') showCity();
      }, 100);
    };

    document.querySelectorAll('[data-city-view]').forEach(button => {
      button.addEventListener('click', () => {
        if (button.dataset.cityView === 'both') showBoth();
        else showCity();
      });
    });

    document.querySelectorAll('[data-forecast-city-link]').forEach(link => {
      if (link.dataset.forecastCityLink !== selected.id) return;
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        showCity();
      });
    });

    cities.forEach(city => {
      const active = city.id === selected.id;
      const icon = L.divIcon({
        className: 'forecast-city-icon city-' + city.id,
        iconSize: [44, 44],
        iconAnchor: [22, 22],
        html: '<a class="forecast-city-pin' + (active ? ' is-selected' : '') +
          '" href="' + cityHref(city) + '" aria-label="Ver as informações de ' +
          city.name + '"' + (active ? ' aria-current="page"' : '') + '>' +
          '<span class="forecast-city-dot" aria-hidden="true"></span>' +
          '<span class="forecast-city-label"><strong>' + city.name + '</strong>' +
          '<small>' + (active ? 'Selecionada' : 'Ver informações') + '</small></span></a>'
      });
      const marker = L.marker([city.lat, city.lon], {
        icon: icon, keyboard: false, zIndexOffset: active ? 1100 : 1000,
        title: 'Informações de ' + city.name
      }).addTo(map);
      if (active) {
        marker.getElement().querySelector('a').addEventListener('click', event => {
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          showCity();
        });
      }
    });

    const hint = L.control({position: 'bottomleft'});
    hint.onAdd = () => {
      const element = L.DomUtil.create('div', 'forecast-map-hint');
      element.innerHTML = '<strong>Escolha Santa Tereza ou Muçum no mapa.</strong>' +
        '<span>Os marcadores indicam cidades; a mancha mostra a água estimada.</span>';
      L.DomEvent.disableClickPropagation(element);
      L.DomEvent.disableScrollPropagation(element);
      return element;
    };
    hint.addTo(map);
    const header = document.querySelector('body > header');
    if (header && typeof ResizeObserver !== 'undefined') {
      const updateLayout = () => {
        document.documentElement.style.setProperty('--forecast-header-height',
          Math.ceil(header.getBoundingClientRect().height) + 'px');
        resize();
      };
      updateLayout();
      new ResizeObserver(updateLayout).observe(header);
      new ResizeObserver(resize).observe(map.getContainer());
    }
    showBoth();
  }

  window.PREVINE_CITY_MAP = {init: init};
})();
