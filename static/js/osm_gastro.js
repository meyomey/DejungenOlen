/* Build z: Mittagstisch-Auswertung im Browser – gleiche Logik wie noon_days()/_lunch_status() in app.py.
   Gebraucht von den Browser-Fallbacks (Direktabfrage bei overpass-api.de), wenn der Server Overpass nicht
   erreicht, und für die einheitlichen Abzeichen in Gastro-Liste, Formular und Tour-Seite.
   Nur Funktionen im globalen Namensraum (onclick-Handler), kein Lookbehind (ältere Safari-Versionen). */

var OSM_LUNCH_DAYS_EN = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
var OSM_LUNCH_DAYS_DE = {Mo: 'Mo', Tu: 'Di', We: 'Mi', Th: 'Do', Fr: 'Fr', Sa: 'Sa', Su: 'So'};
var OSM_LUNCH_DE_WORDS = {montag: 'Mo', dienstag: 'Tu', mittwoch: 'We', donnerstag: 'Th', freitag: 'Fr',
                          samstag: 'Sa', sonnabend: 'Sa', sonntag: 'Su'};
var OSM_CUISINE_DE = {german: 'deutsch', regional: 'regional', local: 'regional', italian: 'italienisch', pizza: 'Pizza',
  pasta: 'Pasta', greek: 'griechisch', burger: 'Burger', kebab: 'Döner', turkish: 'türkisch', asian: 'asiatisch',
  chinese: 'chinesisch', thai: 'thailändisch', vietnamese: 'vietnamesisch', indian: 'indisch', sushi: 'Sushi',
  japanese: 'japanisch', fish: 'Fisch', seafood: 'Fisch & Meeresfrüchte', steak_house: 'Steakhaus',
  international: 'international', bavarian: 'bayrisch', austrian: 'österreichisch', french: 'französisch',
  spanish: 'spanisch', tapas: 'Tapas', mexican: 'mexikanisch', american: 'amerikanisch', coffee_shop: 'Kaffee & Kuchen',
  cake: 'Kuchen', ice_cream: 'Eis', breakfast: 'Frühstück', sausage: 'Wurst', friture: 'Frittiertes', chicken: 'Hähnchen',
  bistro: 'Bistro', crepe: 'Crêpes', pancake: 'Pfannkuchen', vegetarian: 'vegetarisch', vegan: 'vegan', barbecue: 'Grill',
  fine_dining: 'gehobene Küche', bakery: 'Backwaren', sandwich: 'Sandwiches', noodle: 'Nudeln', balkan: 'Balkan',
  croatian: 'kroatisch', portuguese: 'portugiesisch', frisian: 'friesisch', lunch: 'Mittagstisch', soup: 'Suppen',
  potato: 'Kartoffelgerichte', dumplings: 'Klöße'};

function osmOhNormalize(text) {
  var s = String(text).replace(/[–—−]/g, '-').replace(/\|\|/g, ';');
  s = s.replace(/(\d)\s*h\b/gi, '$1 ').replace(/\bUhr\b/gi, ' ');
  s = s.replace(/\b(?:täglich|taeglich|daily|jeden Tag|alle Tage)\b/gi, 'Mo-Su');
  s = s.replace(/\bbis\b/gi, '-');
  s = s.replace(/\b(montags?|dienstags?|mittwochs?|donnerstags?|freitags?|samstags?|sonnabends?|sonntags?)\b/gi,
                function (w) { return OSM_LUNCH_DE_WORDS[w.toLowerCase().replace(/s$/, '')] || w; });
  s = s.replace(/\b(Di|Mi|Do|So)\b\.?/g, function (m, d) { return {Di: 'Tu', Mi: 'We', Do: 'Th', So: 'Su'}[d]; });
  s = s.replace(/\bFeiertage?n?s?\b/gi, 'PH').replace(/\bRuhetage?\s*:\s*/gi, 'Ruhetag ');
  return s;
}

/* Öffnungszeiten → {0..6: [[start, ende], …] | [] | null} (Minuten; 0 = Montag) oder null */
function osmOhWeek(text) {
  if (!text) return null;
  var s = osmOhNormalize(text);
  var re = /(;)|(24\/7)|(\d{1,2})(?:[:.](\d{2}))?\s*-\s*(\d{1,2})(?:[:.](\d{2}))?|(\d{1,2})(?:[:.](\d{2}))?\+|\b(Mo|Tu|We|Th|Fr|Sa|Su)\b(?:\s*-\s*\b(Mo|Tu|We|Th|Fr|Sa|Su)\b)?|\b(off|closed|geschlossen|Ruhetag|OFF)\b|\b(PH|SH)\b/g;
  var groups = [];
  function fresh() { return {days: [], times: [], off: false, hol: false, explicit: true}; }
  function flush(g) {
    if (!(g.times.length || g.off)) {
      if (g.days.length && !g.hol) g.times = [[0, 1440]]; else return;
    }
    if (!g.days.length) {
      if (g.hol) return;
      g.days = [0, 1, 2, 3, 4, 5, 6]; g.explicit = false;
    }
    groups.push(g);
  }
  var g = fresh(), m;
  while ((m = re.exec(s)) !== null) {
    var prev = m.index > 0 ? s.charAt(m.index - 1) : '';
    var next = s.charAt(m.index + m[0].length);
    if (m[1]) { flush(g); g = fresh(); continue; }
    if (m[12]) { g.hol = true; continue; }
    if (m[9]) {
      if (g.days.length && (g.times.length || g.off)) { flush(g); g = fresh(); }
      var a = OSM_LUNCH_DAYS_EN.indexOf(m[9]), rng = [a];
      if (m[10]) {
        var b = OSM_LUNCH_DAYS_EN.indexOf(m[10]); rng = [];
        if (a <= b) { for (var i = a; i <= b; i++) rng.push(i); }
        else { for (var j = a; j < 7; j++) rng.push(j); for (var k = 0; k <= b; k++) rng.push(k); }
      }
      rng.forEach(function (d) { if (g.days.indexOf(d) < 0) g.days.push(d); });
      continue;
    }
    if (m[11]) { g.off = true; g.times = []; continue; }
    if (m[2]) { g.times.push([0, 1440]); continue; }
    if (/\d/.test(prev) || /\d/.test(next)) continue;              // Teil einer längeren Zahl (Jahr, PLZ)
    if (m[7]) {
      var h3 = +m[7], mi3 = +(m[8] || 0);
      if (h3 <= 24 && mi3 < 60) g.times.push([h3 * 60 + mi3, 1440]);
      continue;
    }
    var h1 = +m[3], m1 = +(m[4] || 0), h2 = +m[5], m2 = +(m[6] || 0);
    if (h1 > 24 || h2 > 24 || m1 >= 60 || m2 >= 60) continue;
    var st = h1 * 60 + m1, en = h2 * 60 + m2;
    if (en <= st) en += 1440;
    g.times.push([st, en]);
  }
  flush(g);
  if (!groups.length) return null;
  var week = {0: null, 1: null, 2: null, 3: null, 4: null, 5: null, 6: null};
  groups.forEach(function (x) { x.days.forEach(function (d) { week[d] = x.off ? [] : x.times.slice(); }); });
  if (groups.some(function (x) { return x.explicit && !x.off; })) {
    for (var d2 = 0; d2 < 7; d2++) if (week[d2] === null) week[d2] = [];
  }
  return week;
}

function osmWeekHasTimes(week) {
  if (!week) return false;
  for (var d = 0; d < 7; d++) if (week[d] && week[d].length) return true;
  return false;
}

/* Wochentage (deutsche Kürzel), an denen mittags geöffnet ist (12:45 Uhr offen, ≥ 60 min zwischen 12 und 14 Uhr) */
function osmNoonDays(text, kitchen) {
  var week = kitchen ? osmOhWeek(kitchen) : null;
  if (!osmWeekHasTimes(week)) week = osmOhWeek(text);
  if (!osmWeekHasTimes(week)) return null;
  var out = [];
  for (var d = 0; d < 7; d++) {
    var wins = week[d] || [];
    for (var i = 0; i < wins.length; i++) {
      var a = wins[i][0], b = wins[i][1];
      if (a <= 765 && 765 < b && Math.min(b, 840) - Math.max(a, 720) >= 60) { out.push(OSM_LUNCH_DAYS_DE[OSM_LUNCH_DAYS_EN[d]]); break; }
    }
  }
  return out;
}

function osmDaysDe(codesDe) {               // ['Mo','Di','Mi','Do','Fr'] → „Mo–Fr“, alle sieben → „täglich“
  var order = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  var idx = (codesDe || []).map(function (c) { return order.indexOf(c); }).filter(function (i) { return i >= 0; }).sort(function (a, b) { return a - b; });
  if (idx.length === 7) return 'täglich';
  var runs = [], run = [];
  idx.forEach(function (i) { if (run.length && i !== run[run.length - 1] + 1) { runs.push(run); run = []; } run.push(i); });
  if (run.length) runs.push(run);
  return runs.map(function (r) { return r.length >= 3 ? order[r[0]] + '–' + order[r[r.length - 1]] : r.map(function (i) { return order[i]; }).join(', '); }).join(', ');
}

function osmLunchFromTags(t) {              // lunch=*, lunch:menu/buffet/specials/tourist_menu=* → {lunch, lunch_text}
  var main = (t.lunch || '').trim();
  if (main.toLowerCase() === 'no') return {lunch: 'no', lunch_text: ''};
  var parts = [], labels = {menu: 'Mittagsmenü', buffet: 'Buffet', specials: 'Tagesgerichte', tourist_menu: 'Touristenmenü'};
  if (main && main.toLowerCase() !== 'yes') parts.push({menu: 'Mittagsmenü', buffet: 'Buffet'}[main.toLowerCase()] || main);
  Object.keys(labels).forEach(function (k) {
    var v = (t['lunch:' + k] || '').trim();
    if (v && v.toLowerCase() !== 'no') parts.push(labels[k] + (v.toLowerCase() === 'yes' ? '' : ' ' + v));
  });
  if (main || parts.length) return {lunch: 'yes', lunch_text: parts.join(' · ').slice(0, 200)};
  return {lunch: null, lunch_text: ''};
}

function osmCuisineDe(value) {
  var out = [];
  String(value || '').split(/[;,]/).forEach(function (v) {
    v = v.trim().toLowerCase();
    if (v) { var de = OSM_CUISINE_DE[v] || v.replace(/_/g, ' '); if (out.indexOf(de) < 0) out.push(de); }
  });
  return out.join(', ');
}

function osmLunchStatus(lunch, lunchText, noonDays) {   // → {lunch_status, lunch_label}
  lunchText = (lunchText || '').trim();
  if (lunch === 'yes') return {lunch_status: 'yes', lunch_label: '🍽️ Mittagstisch' + (lunchText ? ': ' + lunchText : '')};
  if (lunch === 'no') return {lunch_status: 'no', lunch_label: 'kein Mittagstisch' + (lunchText ? ' (' + lunchText + ')' : '')};
  if (noonDays && noonDays.length) return {lunch_status: 'noon', lunch_label: '🕛 mittags geöffnet' + (noonDays.length === 7 ? '' : ' ' + osmDaysDe(noonDays))};
  if (noonDays) return {lunch_status: 'noon_closed', lunch_label: 'mittags geschlossen'};
  return {lunch_status: null, lunch_label: ''};
}

/* OSM-Treffer (Browser-Fallback) um dieselben Felder ergänzen wie _lunch_enrich_result() im Server */
function osmLunchEnrich(item, tags) {
  var lt = osmLunchFromTags(tags || {});
  item.lunch = lt.lunch; item.lunch_text = lt.lunch_text;
  item.kitchen_hours = (tags || {})['opening_hours:kitchen'] || '';
  item.cuisine = osmCuisineDe((tags || {}).cuisine);
  var days = osmNoonDays(item.opening_hours, item.kitchen_hours);
  item.noon_days = days || []; item.noon_known = days !== null;
  var st = osmLunchStatus(item.lunch, item.lunch_text, days);
  item.lunch_status = st.lunch_status; item.lunch_label = st.lunch_label;
  return item;
}

/* Abzeichen für Listen und Popups – r braucht lunch_status/lunch_label (optional lunch_text) */
function lunchBadgeHtml(r, extraClass) {
  var st = r && r.lunch_status, lbl = (r && r.lunch_label) || '', cls = extraClass || 'ms-1';
  if (!st) return '';
  if (st === 'yes') return '<span class="badge bg-warning text-dark ' + cls + '" title="' + escHtml(r.lunch_text || 'Mittagstisch') + '">' + escHtml(lbl) + '</span>';
  if (st === 'noon') return '<span class="badge bg-success-subtle text-success border border-success-subtle ' + cls + '" title="aus den Öffnungszeiten abgeleitet">' + escHtml(lbl) + '</span>';
  if (st === 'noon_closed') return '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle ' + cls + '" title="laut Öffnungszeiten zwischen 12 und 14 Uhr nicht geöffnet">' + escHtml(lbl) + '</span>';
  return '<span class="badge bg-light text-muted border ' + cls + '">' + escHtml(lbl) + '</span>';
}

/* Filter „Mittagstisch“: day = '' (irgendein Tag) oder deutsches Kürzel ('Mo'…'So') */
function lunchMatches(r, day) {
  var days = (r && r.noon_days) || [];
  if (!r || !r.lunch_status) return false;
  if (r.lunch_status === 'yes') return !day || !days.length || days.indexOf(day) >= 0;
  if (r.lunch_status === 'noon') return !day || days.indexOf(day) >= 0;
  return false;
}
