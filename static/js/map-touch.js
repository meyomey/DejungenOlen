/* Build bb: Mobiler Karten-Guard – EIN Muster für ALLE Leaflet-Karten der App.
 *
 * Problem: Eine sofort „aktive" Karte frisst dem Handy-Scrollen das Wischen weg –
 * ein Finger zieht die Karte, statt die Seite zu scrollen.
 *
 * Lösung (Standard bei Karten-Einbettungen, wie Leaflet.GestureHandling oder
 * Google-Maps-Embeds): Die Karte startet auf Handys ohne Ein-Finger-Ziehen und
 * zeigt ein Overlay „Karte zum Verschieben antippen". Ein Tipp macht sie beweglich, ein
 * 🔒-Knopf sperrt sie wieder. Zwei-Finger-Gesten (Zoomen/Verschieben) funktionieren
 * jederzeit – deshalb stört der Schutz niemanden, der bewusst mit der Karte arbeitet.
 *
 * Optionen je Karte:
 *   L.map(el, { mobileGuard: false })        → Schutz aus (z. B. Druckansicht)
 *   <div data-map-guard="off"> … </div>      → Schutz aus (Container-Markierung)
 *   <div data-map-guard-hint="Text"> … </div>→ eigener Hinweistext im Overlay
 */
(function () {
  'use strict';

  // Build as: EIN Schloss-Symbol fuer alle Karten (hier und in live.html identisch).
  var LOCK_SVG = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" ' +
                 'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
                 '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5"/>' +
                 '<path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg>';

  function applyGuard(map) {
    if (window.innerWidth >= 992) return;               // Desktop: alles wie bisher
    var box = map.getContainer();
    if (box.dataset.mapGuard === 'off') return;
    if (box.querySelector('.mt-guard-overlay')) return; // doppelt abgesichert

    map.dragging.disable();
    if (map.tap && map.tap.disable) map.tap.disable();  // touchZoom bleibt AN → zwei Finger klappen immer

    var hint = box.dataset.mapGuardHint ||
               '<i class="bi bi-hand-index me-1"></i>Karte zum Verschieben antippen';   // Build 11-06q: eindeutig (bezog sich vorher mehr auf die Tour als auf die Karte)
    // Build aq: Der Hinweis sass MITTIG und verdeckte genau die Kartenmitte – dort, wo man
    // hinschaut („Das stoert mich, es liegt in der Mitte. Sollte vielleicht weiter unten
    // liegen?"). Jetzt unten in der Mitte, ueber der Quellenangabe: oben links ist der Zoom,
    // oben rechts der Kartenstil-Knopf, unten rechts die Quellenangabe – unten in der Mitte
    // ist die einzige Ecke, die frei bleibt.
    //
    // Die Karten sind sehr unterschiedlich hoch (100 px Startseite bis 624 px Karten-Seite).
    // Build aq hatte deshalb kleinere Schrift auf niedrigen Karten – Build as gibt das wieder
    // auf: eine einheitliche Optik ist wichtiger (Nutzerwunsch), und die feste Kante von 11 px
    // haelt den Knopf auf jeder Hoehe ueber der Quellenangabe (17 px hoch).
    var overlay = document.createElement('div');
    overlay.className = 'mt-guard-overlay';
    overlay.style.cssText = 'position:absolute;inset:0;z-index:1000;display:flex;' +
      'align-items:flex-end;justify-content:flex-start;cursor:pointer;border-radius:inherit';
    // Build as: „Die Darstellung des Schlosses sind momentan unterschiedlich Live-Karte und
    // andere Karten. Das sollte einheitlich sein." Deshalb uebernimmt diese Datei exakt die
    // Werte der Live-Karte (#live-guard-lock / #live-guard-pill):
    //   Ecke      unten LINKS (left: 8px) – dort, wo auch die Live-Karte ihren Knopf hat
    //   Grund     rgba(20,30,60,.88), weisse Schrift, Radius 20 px, Schatten 0 1px 5px
    //   Hoehe     34 px = 14 px Innenabstand + 20 px Zeile
    //   Kanten    17 px ueber dem unteren Rand, weil dort die Quellenangabe sitzt
    // Der Hinweis erscheint nur im gesperrten Zustand, das Schloss nur im freien – sie sind
    // nie gleichzeitig da und tauschen sich an derselben Stelle aus.
    overlay.style.paddingLeft = '8px';
    overlay.innerHTML = '<div style="background:rgba(20,30,60,.88);color:#fff;' +
      'padding:.45rem .8rem;border-radius:20px;font-size:.85rem;line-height:20px;' +
      'pointer-events:none;margin-bottom:11px;max-width:calc(100% - 16px);' +
      'box-shadow:0 1px 5px rgba(0,0,0,.35)">' + hint + '</div>';

    // Build as: Schloss unten mittig, exakt wie auf der Live-Karte. Vorher stand es oben rechts
    // als 32-px-Kaestchen mit Icon-Font (bi-lock-fill) und schwarzem Grund – die Live-Karte
    // hatte dagegen ein dunkelblaues Emoji-Pill. Jetzt EINE Darstellung:
    //   Geometrie 34 px hoch (14 px Padding + 20 px Zeile), Radius 20 px, Innenabstand .45rem/.7rem
    //   Farbe     rgba(20,30,60,.88) wie #live-guard-lock / #live-guard-pill
    //   Symbol    🔒 als Text (kein Icon-Font; der CDN-Font fehlt offline und auf manchen
    //             Geraeten – dann war das Schloss ein leerer Kasten)
    //   Text      .95rem, weisse Schrift
    // Position: unten mittig, dieselbe Kante wie der Hinweis (margin-bottom 6px).
    // Symbol als Inline-SVG, NICHT als Emoji und nicht als Icon-Font: der Icon-Font kommt vom
    // CDN (unterwegs ohne Netz ein leerer Kasten), und ein 🔒 sieht auf iOS, Android und
    // Windows jedes Mal anders aus. Das SVG ist auf jedem Geraet dasselbe – und es ist
    // Zeichen fuer Zeichen dasselbe wie auf der Live-Karte.
    var lockBtn = document.createElement('button');
    lockBtn.type = 'button';
    lockBtn.innerHTML = LOCK_SVG;
    lockBtn.title = 'Karte sperren – dann scrollt die Seite';
    lockBtn.setAttribute('aria-label', 'Karte sperren');
    lockBtn.className = 'mt-guard-lock';
    // padding:0 + feste 38x34 + flex-Zentrierung = exakt die Geometrie von #live-guard-lock.
    // Mit Innenabstand schrumpfte das SVG auf 16 px und das Schloss wirkte kleiner als auf
    // der Live-Karte; ohne bleibt es bei 17 px wie dort.
    lockBtn.style.cssText = 'position:absolute;left:8px;bottom:11px;z-index:1001;' +
      'background:rgba(20,30,60,.88);color:#fff;border:0;border-radius:20px;' +
      'padding:0;height:34px;width:38px;' +
      'display:none;align-items:center;justify-content:center;cursor:pointer;' +
      'box-shadow:0 1px 5px rgba(0,0,0,.35)';

    function activate() {
      map.dragging.enable();
      if (map.tap && map.tap.enable) map.tap.enable();
      overlay.style.display = 'none';
      lockBtn.style.display = 'flex';
    }
    function deactivate() {
      map.dragging.disable();
      if (map.tap && map.tap.disable) map.tap.disable();
      overlay.style.display = 'flex';
      lockBtn.style.display = 'none';
    }
    overlay.addEventListener('click', activate);
    lockBtn.addEventListener('click', function (e) { e.stopPropagation(); deactivate(); });

    if (getComputedStyle(box).position === 'static') box.style.position = 'relative';
    box.appendChild(lockBtn);
    box.appendChild(overlay);
  }

  if (window.L && window.L.Map) {
    window.L.Map.mergeOptions({ mobileGuard: true });
    window.L.Map.mergeOptions({ mapStyle: '' });          // 'own'/'off' = kein zentraler Stil-Knopf
    window.L.Map.addInitHook(function () { applyGuard(this); });   // gilt für jede Karte
  }
  window.mobileMapGuard = applyGuard;   // für nachträglich erzeugte Karten
})();


/* Build 11-06z: Kartenstil auf JEDER Karte – Standard · Radkarte (CyclOSM) · Luftbild.
 *
 * Vorher hatte nur die Live-Karte einen Stil-Knopf (🚵 Wege, Build 11-06u). Jetzt bekommt
 * jede Leaflet-Karte der App denselben Umschalter als kleinen Knopf in der Ecke:
 *   – erkannt wird die Karte am OSM-Kachelsatz (L.Map.addInitHook + Nachlese beim Laden),
 *   – getauscht wird nur der GRUND-Kachelsatz; Marker, Tracks und Overlays bleiben,
 *   – die Wahl gilt für die ganze Sitzung (sessionStorage djo_map_style) und für alle Karten
 *     der Seite, damit man beim Wechsel nicht jedes Mal neu umschalten muss,
 *   – Ausnahmen: Druckansicht und Seiten mit eigenem Umschalter (data-map-style="off"/"own").
 *
 * Neue Stile kommen hinzu, indem hier ein Eintrag ergänzt wird – der Knopf zählt sie mit.
 */
(function () {
  'use strict';

  var STORE = 'djo_map_style';
  var DEFAULT = 'osm';
  var ALIASES = {cyclosm: 'cyclosm', 'osm': 'osm'};

  var STYLES = {
    osm: {
      label: 'Standard', icon: 'bi-map', emoji: '🗺️',
      url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      options: {maxZoom: 19, attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'}
    },
    cyclosm: {
      label: 'Radkarte', icon: 'bi-bicycle', emoji: '🚵',
      url: 'https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',
      options: {maxZoom: 19, attribution: '&copy; OpenStreetMap &middot; CyclOSM'}
    },
    sat: {
      label: 'Luftbild', icon: 'bi-globe-americas', emoji: '🛰️',
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      options: {maxZoom: 19, attribution: '&copy; Esri &ndash; Source: Esri, DigitalGlobe, USDA FSA, GeoEye, Earthstar Geographics'}
    }
  };
  var ORDER = ['osm', 'cyclosm', 'sat'];
  var maps = [];          // alle ausgestatteten Karten dieser Seite

  function readStyle() {
    try {
      var v = window.sessionStorage.getItem(STORE);
      if (v && STYLES[v]) return v;
    } catch (e) { /* privater Modus */ }
    return DEFAULT;
  }
  function writeStyle(name) {
    try { window.sessionStorage.setItem(STORE, name); } catch (e) {}
  }
  function create(name) {
    var st = STYLES[name] || STYLES[DEFAULT];
    return window.L.tileLayer(st.url, st.options);
  }
  function isOsmBase(layer) {
    var url = layer && layer._url;
    return !!url && url.indexOf('tile.openstreetmap.org') !== -1;
  }

  // Karten untereinander abgleichen: wer die Wahl ändert, zieht die anderen mit.
  function applyEverywhere(name, source) {
    writeStyle(name);
    maps.forEach(function (m) {
      if (m === source || !m._djoStyleApply) return;
      m._djoStyleApply(name, true);
    });
  }

  function decorate(map) {
    var L = window.L;
    if (!L || !map || map._djoStyleDone) return;
    var box = map.getContainer();
    if (!box) return;
    if (box.dataset.mapStyle === 'off' || box.dataset.mapStyle === 'own') return;
    if (map.options && (map.options.mapStyle === 'off' || map.options.mapStyle === 'own')) return;
    if (box.querySelector('.mt-style')) { map._djoStyleDone = true; return; }   // schon ausgestattet

    var base = null;
    map.eachLayer(function (l) { if (!base && isOsmBase(l)) base = l; });
    if (!base) return;                     // keine OSM-Kacheln → nicht unsere Karte
    map._djoStyleDone = true;
    map._djoBase = base;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'mt-style';
    // Platz: oben rechts. Dort liegt aber oft schon etwas – auf der Live-Karte der
    // OSM-/CyclOSM-Hinweis (Lizenz, Build ab), mobil der 🔒-Knopf des Karten-Guards
    // (Build y), auf anderen Karten die Leaflet-Bedienelemente. Deshalb: erst oben rechts,
    // dann nach unten ausweichen, bis der Knopf wirklich frei liegt (Prüfung mit
    // elementFromPoint – so werden auch Leisten erkannt, die über der Karte liegen).
    // Inline-CSS: unabhängig von geladenen Stylesheets (auch im Druck und in Tests)
    btn.style.cssText = 'position:absolute;z-index:1001;right:8px;top:6px;' +
      'background:rgba(20,30,60,.88);color:#fff;border:0;border-radius:8px;' +
      'font-size:.78rem;line-height:1.2;display:inline-flex;flex-direction:row;align-items:center;justify-content:center;gap:4px;' +
      'cursor:pointer;box-shadow:0 1px 5px rgba(0,0,0,.35);font-weight:600;white-space:nowrap;' +
      'max-width:calc(100% - 16px);overflow:hidden;text-overflow:ellipsis;';
    if (getComputedStyle(box).position === 'static') box.style.position = 'relative';

    // Kleine, nicht bedienbare Vorschaukarten (Mini-Karten in Listen) zeigen nur das Symbol –
    // ein Textknopf würde dort den halben Kartenausschnitt verdecken.
    // Kompakt = nur Symbol: kleine Vorschaukarten UND Karten, die schon eine eigene
    // Symbolspalte haben (Live-Karte trägt data-map-style-compact) – dort wäre ein
    // Textknopf zu breit und würde Lizenzhinweis oder Symbole überdecken.
    var tiny = ((box.offsetHeight || 0) > 0 && box.offsetHeight < 200) ||
               box.dataset.mapStyleCompact === '1';
    function paint() {
      var st = STYLES[readStyle()] || STYLES[DEFAULT];
      if (tiny) {
        // nur Symbol: Quadrat mit fester Größe, Emoji statt Icon-Font
        // (Bootstrap Icons kommen vom CDN – unterwegs ohne Netz wären es leere Kästchen)
        btn.innerHTML = '<span class="mt-ico" style="font-size:1.05rem;line-height:1">' + st.emoji + '</span>';
      } else {
        btn.innerHTML = '<span class="mt-ico" style="font-size:1rem;line-height:1">' + st.emoji + '</span>' +
                        '<span>' + st.label + '</span>';
      }
      btn.title = 'Kartenstil: ' + st.label + ' – antippen wechselt (' +
                  ORDER.map(function (k) { return STYLES[k].label; }).join(' · ') +
                  '). Die Wahl gilt für alle Karten.';
      btn.setAttribute('aria-label', 'Kartenstil wechseln, aktuell: ' + st.label);
      // Quadrat (42 × 42) bei „nur Symbol", sonst Textknopf
      btn.style.padding = tiny ? '0' : '5px 9px';
      btn.style.width = tiny ? '42px' : 'auto';
      btn.style.height = tiny ? '42px' : 'auto';
    }

    // Freie Ecke suchen: oben rechts starten, bei Überdeckung nach unten rücken.
    function freeSpot() {
      var r = btn.getBoundingClientRect();
      if (!r.width || !r.height) return true;          // (noch) nicht sichtbar → nichts tun
      var pts = [[r.left + 6, r.top + r.height / 2], [r.right - 6, r.top + r.height / 2],
                 [r.left + r.width / 2, r.top + 4], [r.left + r.width / 2, r.bottom - 4]];
      // Der Knopf liegt mit z-index 1001 selbst obenauf – für die Messung kurz ausblenden,
      // sonst findet elementFromPoint immer nur den Knopf selbst.
      var vis = btn.style.visibility;
      btn.style.visibility = 'hidden';
      var frei = true;
      // 1) Leaflet-Bedienelemente und 🔒 in der Karte: Rechtecke dürfen sich nicht schneiden
      //    (auch ein paar überdeckte Pixel des Lizenzhinweises zählen).
      var ctrls = box.querySelectorAll('.leaflet-control, .mt-guard-lock');
      for (var c = 0; c < ctrls.length && frei; c++) {
        var o = ctrls[c];
        if (o === btn || o.contains(btn) || btn.contains(o) || !o.getClientRects().length) continue;
        var q = o.getBoundingClientRect();
        if (q.width && q.height && !(r.right <= q.left || r.left >= q.right ||
                                     r.bottom <= q.top || r.top >= q.bottom)) frei = false;
      }
      // 2) Fremde Elemente über der Karte (Leisten, feste Knöpfe) per Trefferprobe
      for (var i = 0; i < pts.length && frei; i++) {
        var el = document.elementFromPoint(pts[i][0], pts[i][1]);
        // Alles, was zur Karte gehört (Kacheln, Bedienelemente, Overlays), ist in Ordnung –
        // nur fremde Elemente (Leisten, Knöpfe, Hinweise) sind ein Hindernis.
        if (el && !(el === btn || btn.contains(el) || box.contains(el))) { frei = false; break; }
      }
      btn.style.visibility = vis;
      return frei;
    }
    function place() {
      btn.style.top = '6px';
      btn.style.right = '8px';                     // Build as: immer erst die Grundecke setzen
      var guard = box.querySelector('.mt-guard-lock');
      if (guard && guard.getClientRects().length) {
        // Build as: Das 🔒 sitzt nicht mehr oben rechts, sondern unten mittig. Nur wenn es
        // wirklich in derselben Zeile liegt (vertikale Überlappung), muss der Stil-Knopf
        // ausweichen – sonst schob die alte Rechnung ihn grundlos nach links.
        var g = guard.getBoundingClientRect(), b = btn.getBoundingClientRect();
        var gleicheZeile = g.top < b.bottom && g.bottom > b.top;
        if (gleicheZeile && g.width && b.width && g.left < b.right) {
          btn.style.right = (b.right - g.left + 8) + 'px';
        }
      }
      for (var i = 0; i < 8 && !freeSpot(); i++) {
        btn.style.top = (parseFloat(btn.style.top) + 34) + 'px';
      }
    }

    function setStyle(name, quiet) {
      if (!STYLES[name]) name = DEFAULT;
      if (map._djoBase) map.removeLayer(map._djoBase);
      map._djoBase = create(name);
      map._djoBase.addTo(map);
      if (map._djoBase.bringToBack) map._djoBase.bringToBack();   // Punkte/Linien bleiben oben
      // Reihenfolge zählt: erst die Wahl merken (applyEverywhere), DANN malen –
      // sonst zeigt der Knopf nach dem Klick noch den alten Stil an (Build z).
      if (!quiet) applyEverywhere(name, map);
      paint();
    }
    map._djoStyleApply = setStyle;

    // Gespeicherte Wahl beim Aufbau anwenden
    var wanted = readStyle();
    if (wanted !== DEFAULT) setStyle(wanted, true);

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var next = ORDER[(ORDER.indexOf(readStyle()) + 1) % ORDER.length];
      setStyle(next);
      try { document.dispatchEvent(new CustomEvent('djo-map-style', {detail: {style: next}})); } catch (err) {}
    });
    paint();
    box.appendChild(btn);
    [0, 250, 800].forEach(function (ms) { setTimeout(place, ms); });
    window.addEventListener('resize', function () { setTimeout(place, 100); });
    if (box._djoMap === undefined) box._djoMap = map;
    maps.push(map);

    // Seiten mit EIGENEM Umschalter (z. B. Tourseite OSM/Satellit) bekommen keinen zweiten Knopf –
    // aber wenn dort umgeschaltet wird, sollen die übrigen Karten der Seite folgen.
    box.addEventListener('djo-style-sync', function (e) {
      if (e.detail && STYLES[e.detail.style]) setStyle(e.detail.style, true);
    });
  }

  function initAll() {
    document.querySelectorAll('.leaflet-container').forEach(function (el) {
      var m = el._djoMap;
      if (m) decorate(m);
    });
  }

  if (window.L && window.L.Map) {
    window.L.Map.addInitHook(function () {
      var box = this.getContainer();
      if (box) box._djoMap = this;         // Rückweg DOM → Karte für die Nachlese
      var m = this;
      // Viele Seiten legen den Kachelsatz erst nach L.map() an → kurz warten.
      setTimeout(function () { decorate(m); }, 60);
    });
  }
  document.addEventListener('DOMContentLoaded', function () { setTimeout(initAll, 150); });
  window.addEventListener('load', function () { setTimeout(initAll, 300); });

  // Öffentliche API (auch für Tests und für Seiten mit eigenem Umschalter)
  window.djoMap = {
    styles: STYLES,
    order: ORDER,
    current: readStyle,
    set: function (name) { applyEverywhere(name, null); },
    syncOthers: function (name, box) {
      // von einer Seite mit eigenem Umschalter aufrufen: alle anderen Karten nachziehen
      writeStyle(name);
      document.querySelectorAll('.leaflet-container').forEach(function (el) {
        var m = el._djoMap;
        if (m && m._djoStyleApply) m._djoStyleApply(name, true);
      });
    },
    decorate: decorate,
    // Karten, die ihren Stil selbst verwalten (data-map-style="own"), können sich hier
    // einen passenden Kachelsatz holen – so bleibt es bei EINER Definition der Quellen.
    layer: function (name) { return create(name); },
    apply: function (map, name) {
      if (map && map._djoStyleApply) { map._djoStyleApply(name, true); }
    }
  };
})();
