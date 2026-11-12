"""Build cc: WhatsApp-Einladung im Admin-Bereich – Karte wechselt mit dem Mitglied, PC → WhatsApp Web.

**Meldung:**
    „Es bleibt immer das gleiche WhatsApp Fenster offen, auch wenn ich ein anderes Mitglied
    auswähle. Ich benutze auch Web WhatsApp. Der Link lässt sich nicht direkt darin öffnen
    sondern es kommt eine Meldung.“ (Windows: „Der Datei ist keine App zum Ausführen dieser
    Aktion zugeordnet“ – URL `whatsapp://send/?text=…`)

**Nachgemessen (templates/admin/dashboard.html, app.py admin_dashboard):**
1. Die grüne Karte „Einladungstext für WhatsApp“ zeigte nur den Link aus `?invite=<id>`,
   den die Weiterleitung nach „Link erstellen“ setzt. Die „WhatsApp“-Links in der Liste
   gingen direkt zu wa.me und änderten die Karte nie → oben blieb immer dasselbe Mitglied.
2. Alle Links zeigten auf `https://wa.me/?text=…`. Am PC leitet wa.me auf `whatsapp://`
   (Desktop-App) weiter; ohne installierte App kommt der Windows-Dialog. WhatsApp Web
   braucht `https://web.whatsapp.com/send?text=…`.

**Fix:** Listen-Links (`.js-invite-pick`, Delegation, da die Liste unter dem Skript liegt)
laden den Text des angeklickten Mitglieds in die Karte (Name im Kopf) – ohne JS führen sie
auf `/admin/?invite=<id>#einladung`. Der Senden-Button wählt per User-Agent: Handy → wa.me,
PC → web.whatsapp.com. Nachgestellt mit jsdom (Windows- und iPhone-UA): nach Klick auf
„Jörg Krüger“ steht Jörg in Karte, Kopf und Link.
"""
import os
import re

from tests.base import AppTestCase, appmod

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(rel):
    with open(os.path.join(_ROOT, rel), encoding='utf-8') as f:
        return f.read()


class EinladungsKarteTest(AppTestCase):
    def _zwei_einladungen(self):
        self.login_admin()
        r1 = self.client.post('/admin/einladen', data={'label': 'Axel Hübner'})
        r2 = self.client.post('/admin/einladen', data={'label': 'Jörg Krüger'})
        self.assertIn('?invite=', r1.headers['Location'])
        self.assertIn('#einladung', r2.headers['Location'])
        return r1.headers['Location'].split('#')[0], r2.headers['Location'].split('#')[0]

    def test_karte_zeigt_den_link_aus_der_url(self):
        url1, url2 = self._zwei_einladungen()
        html = self.client.get(url1).get_data(as_text=True)
        ta = re.search(r'<textarea id="invite-text"[^>]*>(.*?)</textarea>', html, re.S).group(1)
        self.assertTrue(ta.startswith('Hallo Axel Hübner!'))
        self.assertIn('– Axel Hübner', html)
        html2 = self.client.get(url2).get_data(as_text=True)
        ta2 = re.search(r'<textarea id="invite-text"[^>]*>(.*?)</textarea>', html2, re.S).group(1)
        self.assertTrue(ta2.startswith('Hallo Jörg Krüger!'))

    def test_listen_links_wechseln_die_karte_statt_wa_me(self):
        """Vorher: <a href="https://wa.me/?text=…" class="small text-success">. Nachher: js-invite-pick."""
        url1, _ = self._zwei_einladungen()
        html = self.client.get(url1).get_data(as_text=True)
        self.assertEqual(len(re.findall(r'href="https://wa\.me[^"]*"[^>]*class="small text-success"', html)), 0,
                         'Listen-Links dürfen nicht mehr direkt zu wa.me springen')
        picks = re.findall(r'<a href="([^"]+)" data-invite="(\d+)"\s+class="small text-success js-invite-pick"', html)
        self.assertGreaterEqual(len(picks), 2)
        for href, inv_id in picks:
            self.assertEqual(href, f'/admin/?invite={inv_id}#einladung', 'Fallback ohne JavaScript')

    def test_alle_texte_und_namen_liegen_im_skript(self):
        url1, _ = self._zwei_einladungen()
        html = self.client.get(url1).get_data(as_text=True)
        self.assertIn('Hallo J\\u00f6rg Kr\\u00fcger!', html)       # tojson escapt Nicht-ASCII
        self.assertIn('"J\\u00f6rg Kr\\u00fcger"', html)
        self.assertIn("document.addEventListener('click'", html, 'Delegation – Liste steht unter dem Skript')
        self.assertIn('.js-invite-pick', html)

    def test_karte_ohne_url_parameter_ist_versteckt_aber_da(self):
        """Ohne ?invite= ist die Karte da (für den Klick), aber d-none – kein Inline-display."""
        self._zwei_einladungen()
        html = self.client.get('/admin/').get_data(as_text=True)
        m = re.search(r'<div class="card shadow-sm border-success mb-3 ([^"]*)" id="einladung">', html)
        self.assertIsNotNone(m)
        self.assertIn('d-none', m.group(1))
        self.assertNotIn('style="display', html[m.start():m.start() + 400])

    def test_ohne_offene_einladungen_keine_karte(self):
        from tests.base import app as flask_app, db, M
        self.login_admin()
        with flask_app.app_context():
            M.InviteToken.query.filter_by(used=False).update({'used': True})
            db.session.commit()
        html = self.client.get('/admin/').get_data(as_text=True)
        self.assertNotIn('id="einladung"', html)


class WhatsAppWebTest(AppTestCase):
    def test_pc_nutzt_whatsapp_web_handy_die_app(self):
        tpl = _lies('templates/admin/dashboard.html')
        self.assertIn("'https://web.whatsapp.com/send?text='", tpl)
        self.assertIn("'https://wa.me/?text='", tpl)
        self.assertRegex(tpl, r"mobile=/Android\|iPhone\|iPad\|iPod/i\.test\(navigator\.userAgent\)")
        self.assertIn('am PC WhatsApp Web', tpl)

    def test_build_stempel(self):
        self.assertEqual(appmod.APP_BUILD, '2026-11-12 cc')
