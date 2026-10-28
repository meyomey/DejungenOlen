/* Build bb: Mobiler Karten-Guard – EIN Muster für ALLE Leaflet-Karten der App.
 *
 * Problem: Eine sofort „aktive" Karte frisst dem Handy-Scrollen das Wischen weg –
 * ein Finger zieht die Karte, statt die Seite zu scrollen.
 *
 * Lösung (Standard bei Karten-Einbettungen, wie Leaflet.GestureHandling oder
 * Google-Maps-Embeds): Die Karte startet auf Handys ohne Ein-Finger-Ziehen und
 * zeigt ein Overlay „Tippen zum Aktivieren". Ein Tipp macht sie beweglich, ein
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

  function applyGuard(map) {
    if (window.innerWidth >= 992) return;               // Desktop: alles wie bisher
    var box = map.getContainer();
    if (box.dataset.mapGuard === 'off') return;
    if (box.querySelector('.mt-guard-overlay')) return; // doppelt abgesichert

    map.dragging.disable();
    if (map.tap && map.tap.disable) map.tap.disable();  // touchZoom bleibt AN → zwei Finger klappen immer

    var hint = box.dataset.mapGuardHint ||
               '<i class="bi bi-hand-index me-1"></i>Tippen zum Aktivieren';
    var overlay = document.createElement('div');
    overlay.className = 'mt-guard-overlay';
    overlay.style.cssText = 'position:absolute;inset:0;z-index:1000;display:flex;' +
      'align-items:center;justify-content:center;cursor:pointer;border-radius:inherit';
    overlay.innerHTML = '<div style="background:rgba(0,0,0,.45);color:#fff;' +
      'padding:8px 16px;border-radius:20px;font-size:.85rem;pointer-events:none">' + hint + '</div>';

    var lockBtn = document.createElement('button');
    lockBtn.type = 'button';
    lockBtn.innerHTML = '<i class="bi bi-lock-fill"></i>';
    lockBtn.title = 'Karte sperren';
    lockBtn.setAttribute('aria-label', 'Karte sperren');
    lockBtn.style.cssText = 'position:absolute;top:8px;right:8px;z-index:1001;' +
      'background:rgba(0,0,0,.5);color:#fff;border:0;border-radius:6px;width:32px;height:32px;' +
      'cursor:pointer;font-size:.9rem;display:none';

    function activate() {
      map.dragging.enable();
      if (map.tap && map.tap.enable) map.tap.enable();
      overlay.style.display = 'none';
      lockBtn.style.display = 'block';
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
    window.L.Map.addInitHook(function () { applyGuard(this); });   // gilt für jede Karte
  }
  window.mobileMapGuard = applyGuard;   // für nachträglich erzeugte Karten
})();
