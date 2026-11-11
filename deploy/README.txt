Deploy-Pakete – De jungen Olen
==============================

Hier liegen immer nur die Pakete des AKTUELLEN Builds. Ältere Builds werden
beim nächsten Mal entfernt (sie sind in der Git-Historie weiterhin zu finden,
falls doch mal eines gebraucht wird).

Aktueller Stand: Build 2026-11-09 by  → siehe LAST_DEPLOY.txt


WELCHES PAKET?
--------------
…_aenderungen.zip
    Nur die geänderten Dateien seit dem letzten Server-Stand. Das normale
    Paket zum Aktualisieren. Klein, schnell hochgeladen.

…_komplett.zip
    Die ganze App. Für den ersten Upload, zum Neuaufsetzen oder wenn man
    unsicher ist, ob der Server vollständig ist.


UPLOAD
------
ZIP entpacken und den Inhalt mit gleicher Ordnerstruktur per FTP in den
App-Ordner (…/dejungen_olen/) kopieren, vorhandene Dateien überschreiben.
Die Hinweise im Paket (_DEPLOY_HINWEISE.txt) nennen die Einzelheiten.


NACH DEM UPLOAD
---------------
1. Passenger neu starten: Plesk → Python → Restart
   (oder tmp/restart.txt anfassen).
2. Footer prüfen: Dort muss die Build-Nummer aus LAST_DEPLOY.txt stehen.
   Steht dort eine ältere, wurde nicht alles hochgeladen.
3. ffmpeg-Rechte 755 setzen, falls die Datei neu hochgeladen wurde.


NICHT IM PAKET (bleibt auf dem Server unverändert)
--------------------------------------------------
.env, instance/*.db, static/uploads/, backups/, venv/, ffmpeg
