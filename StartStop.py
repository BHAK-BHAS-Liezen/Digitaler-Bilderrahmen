"""
╔══════════════════════════════════════════════════════════════╗
║           Digitaler Bilderrahmen — Hauptprogramm             ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import time
import threading
import subprocess
import logging
import json
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from gpiozero import MotionSensor, Button

# ──────────────────────────────────────────────────────────────
#  KONFIGURATION
# ──────────────────────────────────────────────────────────────

GPIO_PIN        = 4       # GPIO-Pin wo der PIR-Sensor angeschlossen ist
MIC_GPIO_PIN    = 17      # GPIO-Pin vom KY-038 Mikrofon (DO = Digital Out)

WARMUP_SEC      = 30      # PIR braucht ~30s zum Kalibrieren nach dem Start
TIMEOUT_SEC     = 30      # Nach 30s ohne Aktivität → Monitor aus
CONFIRM_COUNT   = 3       # PIR muss 3x in Folge Bewegung melden → kein Fehlalarm
CHECK_INTERVAL  = 0.1     # Sensoren werden 10x pro Sekunde abgefragt

MIC_COOLDOWN    = 2.0     # Pause nach Geräusch — verhindert 100x-Aktivierung

GDRIVE_REMOTE   = "gdrive:Bilder"                                  # rclone Remote-Name
LOCAL_IMAGE_DIR = "/home/admin/Digitaler-Bilderrahmen/bilder"      # Lokaler Bildordner

LOG_DATEI      = "/home/admin/Digitaler-Bilderrahmen/bilderrahmen.log"
ÄNDERUNGEN_LOG = "/home/admin/Digitaler-Bilderrahmen/änderungen.log"
SYNC_INTERVAL  = 60       # Alle 60s mit Google Drive synchronisieren

WEB_DIR  = "/home/admin/Digitaler-Bilderrahmen"
WEB_PORT = 8080           # Chromium öffnet http://localhost:8080
VOLLBILD = False          # True = Kiosk-Modus (kein Fensterrand, kein Cursor)

# ──────────────────────────────────────────────────────────────
#  LOGGING
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(threadName)-10s]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),          # → Ausgabe in die Konsole
        logging.FileHandler(LOG_DATEI)    # → gleichzeitig in Datei speichern
    ]
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  GLOBALER ZUSTAND
# ──────────────────────────────────────────────────────────────

state_lock        = threading.Lock()   # Schützt Variablen vor gleichzeitigem Zugriff
screen_on         = True               # Aktueller Monitor-Status
last_motion_time  = datetime.now()     # Zeitpunkt der letzten Aktivität (für Timeout)
motion_active     = False              # PIR meldet gerade Bewegung?
sound_active      = False              # Mikrofon meldet gerade Geräusch?
system_ready      = False              # Aufwärmphase abgeschlossen?
browser_proc      = None               # Handle auf den laufenden Chromium-Prozess

status_datei  = os.path.join(WEB_DIR, "status.txt")          # Wird von der Slideshow gelesen
CONTROL_FILE  = os.path.join(WEB_DIR, "data/control.json")   # Admin-Panel schreibt hier rein
SENSOR_STATUS = os.path.join(WEB_DIR, "data/sensor_status.json")  # Live-Status für Panel

# ──────────────────────────────────────────────────────────────
#  HILFSFUNKTIONEN
# ──────────────────────────────────────────────────────────────

def status_setzen(status: str):
    try:
        with open(status_datei, "w") as f:
            f.write(status)                  # z.B. "active", "sleeping", "warming_up"
        log.info(f"Status → {status}")
    except Exception as e:
        log.warning(f"Status-Datei Fehler: {e}")


def sensor_status_schreiben():
    try:
        daten = {
            "zeitstempel":    datetime.now().strftime("%H:%M:%S"),
            "pir_aktiv":      motion_active,      # True wenn Bewegung erkannt
            "mikrofon_aktiv": sound_active,        # True wenn Geräusch erkannt
            "monitor_an":     screen_on,           # True wenn Monitor läuft
            "system_bereit":  system_ready,        # True nach Aufwärmphase
            "mic_gpio":       MIC_GPIO_PIN,
            "timeout_sek":    TIMEOUT_SEC,
        }
        os.makedirs(os.path.dirname(SENSOR_STATUS), exist_ok=True)
        with open(SENSOR_STATUS, "w") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)   # Als lesbare JSON-Datei
    except Exception as e:
        log.warning(f"Sensor-Status Fehler: {e}")


def aktivitaet_melden(quelle: str):
    global last_motion_time

    with state_lock:
        last_motion_time = datetime.now()    # Timeout-Uhr neu starten

    status_setzen("active")
    monitor_an()                             # Falls Monitor aus war → einschalten
    sensor_status_schreiben()
    log.info(f"Aktivität erkannt [{quelle}]")    # quelle = "PIR" oder "Mikrofon"


def lade_control():
    global TIMEOUT_SEC, screen_on, last_motion_time

    try:
        with open(CONTROL_FILE, "r") as f:
            data = json.load(f)

        TIMEOUT_SEC = data.get("timeout", 30)    # Neuen Timeout-Wert übernehmen

        monitor_status = data.get("monitor", "on")
        
        if monitor_status == "off":
            with state_lock:
                war_an = screen_on
                last_motion_time = datetime.now()    # Timeout zurücksetzen — sonst überschreibt Wächter sofort
            if war_an:
                log.info("Benutzer hat Monitor manuell AUS geschaltet")
                monitor_aus()
            return                                   # Raus — keine automatische Aktivierung
            
        elif monitor_status == "on":
            with state_lock:
                war_aus = not screen_on
                last_motion_time = datetime.now()    # Timeout zurücksetzen
            if war_aus:
                log.info("Benutzer hat Monitor manuell AN geschaltet")
                monitor_an()

    except Exception as e:
        log.warning(f"Control Fehler: {e}")


def änderungen_loggen(neu: set, geloescht: set):
    if not neu and not geloescht:
        return                               # Nichts geändert → nichts loggen
    zeitstempel = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ÄNDERUNGEN_LOG, "a", encoding="utf-8") as f:    # "a" = anhängen, nicht überschreiben
            f.write(f"\n{'─' * 50}\n")
            f.write(f"  Zeitpunkt: {zeitstempel}\n")
            f.write(f"{'─' * 50}\n")
            if neu:
                for bild in sorted(neu):
                    f.write(f"  ✚ HINZUGEFÜGT:  {bild}\n")
            if geloescht:
                for bild in sorted(geloescht):
                    f.write(f"  ✖ ENTFERNT:     {bild}\n")
    except Exception as e:
        log.warning(f"Änderungs-Log Fehler: {e}")


# ──────────────────────────────────────────────────────────────
#  MONITOR & BROWSER STEUERUNG
# ──────────────────────────────────────────────────────────────

def monitor_an():
    global screen_on
    with state_lock:
        bereits_an = screen_on
    if bereits_an:
        return                                    # Schon an → nichts tun
    log.info("▶  Monitor AN")
    os.system("vcgencmd display_power 1")         # Raspberry Pi: HDMI einschalten
    status_setzen("active")
    with state_lock:
        screen_on = True
    sensor_status_schreiben()


def monitor_aus():
    global screen_on
    with state_lock:
        bereits_aus = not screen_on
    if bereits_aus:
        return                                    # Schon aus → nichts tun
    log.info("◼  Monitor AUS — Schlafmodus")
    status_setzen("sleeping")
    time.sleep(1.5)                               # Kurz warten damit Browser "sleeping" anzeigen kann
    os.system("vcgencmd display_power 0")         # Raspberry Pi: HDMI ausschalten
    with state_lock:
        screen_on = False
    sensor_status_schreiben()


def browser_starten():
    global browser_proc
    time.sleep(2)                                 # Warten bis Webserver sicher läuft
    url = f"http://localhost:{WEB_PORT}"
    chromium_cmd = [
        "chromium-browser",
        "--noerrdialogs",                         # Keine Fehlerdialoge beim Start
        "--disable-infobars",                     # Keine "Chromium wird von Software gesteuert"-Leiste
        "--disable-session-crashed-bubble",       # Kein "Wiederherstellungs"-Popup
        "--disable-restore-session-state",        # Letzte Session nicht wiederherstellen
        "--autoplay-policy=no-user-gesture-required",  # Videos/GIFs ohne Klick abspielen
        url
    ]
    if VOLLBILD:
        chromium_cmd += ["--kiosk", "--start-fullscreen"]   # Kiosk = kein Fensterrand
    else:
        chromium_cmd += ["--start-maximized"]               # Normales Fenster maximiert
    try:
        browser_proc = subprocess.Popen(
            chromium_cmd,
            stdout=subprocess.DEVNULL,    # Chromium-Ausgaben nicht ins Terminal
            stderr=subprocess.DEVNULL
        )
        log.info(f"Chromium gestartet — {'Vollbild' if VOLLBILD else 'Fenster'}")
        log.info(f"Slideshow: {url}")
    except FileNotFoundError:
        log.error("Chromium nicht gefunden!")


def browser_stoppen():
    global browser_proc
    if browser_proc and browser_proc.poll() is None:    # Poll() = None bedeutet: läuft noch
        browser_proc.terminate()                        # Sanft beenden (SIGTERM)
        try:
            browser_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            browser_proc.kill()                         # Nach 3s hart beenden (SIGKILL)
    browser_proc = None


# ──────────────────────────────────────────────────────────────
#  THREAD 1: WEBSERVER
# ──────────────────────────────────────────────────────────────

def webserver_thread():
    os.chdir(WEB_DIR)    # Arbeitsverzeichnis wechseln → Dateien werden von hier ausgeliefert

    class LeiserHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass    # HTTP-Anfragen nicht ins Log schreiben (wäre alle 2s Spam)

    server = HTTPServer(("", WEB_PORT), LeiserHandler)
    log.info(f"Webserver läuft auf http://localhost:{WEB_PORT}")
    server.serve_forever()    # Blockiert — läuft dauerhaft in diesem Thread


# ──────────────────────────────────────────────────────────────
#  THREAD 2: PIR-SENSOR (GPIO 4)
# ──────────────────────────────────────────────────────────────

def pir_thread():
    global motion_active, system_ready

    log.info(f"PIR-Sensor wird initialisiert (GPIO {GPIO_PIN})...")

    try:
        pir = MotionSensor(pin=GPIO_PIN, sample_rate=10, threshold=0.5)  # 10 Messungen/s, 50% Schwelle
    except Exception as e:
        log.error(f"PIR-Sensor Fehler: {e}")
        return

    log.info(f"Aufwärmphase: {WARMUP_SEC} Sekunden...")
    status_setzen("warming_up")

    for verbleibend in range(WARMUP_SEC, 0, -5):    # Rückwärts in 5er-Schritten
        log.info(f"  Sensor bereit in {verbleibend}s ...")
        time.sleep(5)

    log.info("PIR-Sensor bereit ✓")
    status_setzen("active")
    system_ready = True    # Signal an andere Threads: jetzt dürfen sie starten

    counter = 0    # Zählt aufeinanderfolgende Bewegungsmeldungen

    while True:
        if pir.motion_detected:
            counter += 1
            if counter >= CONFIRM_COUNT:             # Erst nach 3 Bestätigungen aktivieren
                war_inaktiv = not motion_active
                with state_lock:
                    motion_active = True
                if war_inaktiv:                      # Nur beim Wechsel inaktiv→aktiv melden
                    aktivitaet_melden("PIR")
        else:
            if motion_active:
                log.info("PIR: Keine Bewegung mehr.")
            counter = 0                              # Zähler bei Pause zurücksetzen
            with state_lock:
                motion_active = False
            sensor_status_schreiben()

        time.sleep(CHECK_INTERVAL)    # 0.1s warten → 10 Checks pro Sekunde


# ──────────────────────────────────────────────────────────────
#  THREAD 3: KY-038 MIKROFON (GPIO 17, DO-Pin)
# ──────────────────────────────────────────────────────────────

def mikrofon_thread():
    global sound_active

    while not system_ready:    # Warten bis PIR-Aufwärmphase abgeschlossen
        time.sleep(0.5)

    log.info(f"KY-038 Mikrofon-Thread gestartet (GPIO {MIC_GPIO_PIN})")

    try:
        mic = Button(pin=MIC_GPIO_PIN, pull_up=False, bounce_time=0.05)  # pull_up=False: KY-038 ist aktiv HIGH
        log.info(f"KY-038 Mikrofon bereit ✓ (GPIO {MIC_GPIO_PIN})")
    except Exception as e:
        log.error(f"KY-038 Mikrofon Fehler: {e}")
        log.error(f"Prüfe: DO-Kabel an GPIO {MIC_GPIO_PIN} angeschlossen?")
        return

    letztes_geraeusch = 0    # Unix-Timestamp des letzten Geräuschs (für Cooldown)

    while True:
        if mic.is_pressed:                           # DO-Pin HIGH = Geräusch über Schwellwert
            jetzt = time.time()

            war_inaktiv = not sound_active
            with state_lock:
                sound_active = True

            if war_inaktiv or (jetzt - letztes_geraeusch) > MIC_COOLDOWN:  # Cooldown prüfen
                log.info(f"🔊 Geräusch erkannt (GPIO {MIC_GPIO_PIN})")
                aktivitaet_melden("Mikrofon")
                letztes_geraeusch = jetzt            # Cooldown-Uhr starten

        else:                                        # DO-Pin LOW = Stille
            if sound_active:
                log.info("Mikrofon: Stille")
                with state_lock:
                    sound_active = False
                sensor_status_schreiben()

        time.sleep(CHECK_INTERVAL)


# ──────────────────────────────────────────────────────────────
#  THREAD 4: TIMEOUT-WÄCHTER
# ──────────────────────────────────────────────────────────────

def timeout_thread():
    letzte_warnung = -1    # Verhindert doppelte Log-Einträge für denselben Countdown-Wert

    while True:
        if not system_ready:
            time.sleep(1)
            continue       # Noch in Aufwärmphase → noch nicht aktiv werden

        with state_lock:
            lmt  = last_motion_time
            s_on = screen_on

        inaktiv_seit = datetime.now() - lmt               # Wie lange schon keine Aktivität?
        inaktiv_sek  = int(inaktiv_seit.total_seconds())

        if inaktiv_seit > timedelta(seconds=TIMEOUT_SEC):
            if s_on:
                log.info(f"Keine Aktivität seit {TIMEOUT_SEC}s → Monitor aus.")
                status_setzen("no_motion")
                monitor_aus()

        elif s_on:
            verbleibend = TIMEOUT_SEC - inaktiv_sek
            if verbleibend % 10 == 0 and verbleibend != letzte_warnung and 0 < verbleibend < TIMEOUT_SEC:
                log.info(f"Keine Aktivität — Monitor aus in {verbleibend}s")   # z.B. "noch 20s", "noch 10s"
                letzte_warnung = verbleibend

        time.sleep(1)    # Jede Sekunde prüfen reicht völlig


# ──────────────────────────────────────────────────────────────
#  THREAD 5: GOOGLE DRIVE-SYNC
# ──────────────────────────────────────────────────────────────

def bilder_liste():
    if not os.path.isdir(LOCAL_IMAGE_DIR):
        return set()    # Ordner existiert noch nicht → leeres Set zurückgeben
    return set(
        f for f in os.listdir(LOCAL_IMAGE_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))   # Nur Bilddateien
    )


def gdrive_thread():
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

    while True:
        log.info("Google Drive-Sync wird gestartet...")
        bilder_vorher = bilder_liste()    # Snapshot vor dem Sync → für Vergleich danach

        try:
            result = subprocess.run(
                [
                    "rclone", "sync",
                    GDRIVE_REMOTE,        # Quelle: Google Drive Ordner
                    LOCAL_IMAGE_DIR,      # Ziel: lokaler Ordner auf dem Pi
                    "--include", "*.jpg",
                    "--include", "*.jpeg",
                    "--include", "*.png",
                    "--include", "*.JPG",
                    "--include", "*.PNG",
                    "--include", "*.JPEG",
                    "--transfers", "2",           # Max. 2 Dateien gleichzeitig laden (schont den Pi)
                    "--low-level-retries", "3",   # Bei Verbindungsfehler 3x neu versuchen
                    "--delete-during",            # Gelöschte Drive-Bilder sofort lokal entfernen
                ],
                capture_output=True,
                text=True,
                timeout=180    # Abbruch nach 3 Minuten (Schutz bei hängendem Netz)
            )

            if result.returncode == 0:
                bilder_nachher = bilder_liste()
                neu       = bilder_nachher - bilder_vorher    # Mengensubtraktion: was ist neu?
                geloescht = bilder_vorher  - bilder_nachher   # Mengensubtraktion: was fehlt?
                if neu:
                    log.info(f"  ✚ Neu ({len(neu)}): {', '.join(sorted(neu))}")
                if geloescht:
                    log.info(f"  ✖ Entfernt ({len(geloescht)}): {', '.join(sorted(geloescht))}")
                if not neu and not geloescht:
                    log.info("  ↔ Keine Änderungen")
                änderungen_loggen(neu, geloescht)
                log.info(f"Sync abgeschlossen ✓  ({len(bilder_nachher)} Bilder)")
            else:
                log.warning(f"rclone Fehler: {result.stderr.strip()}")

        except FileNotFoundError:
            log.error("rclone nicht gefunden!")       # rclone nicht installiert
        except subprocess.TimeoutExpired:
            log.warning("Sync Timeout.")              # Netz zu langsam oder hängt
        except Exception as e:
            log.error(f"Sync-Fehler: {e}")

        log.info(f"Nächster Sync in {SYNC_INTERVAL}s.")
        time.sleep(SYNC_INTERVAL)    # Pause bis zum nächsten Sync


# ──────────────────────────────────────────────────────────────
#  THREAD 6: CONTROL-DATEI POLLING
# ──────────────────────────────────────────────────────────────

def control_thread():
    while True:
        lade_control()    # Alle 2s prüfen ob Admin-Panel Änderungen geschrieben hat
        time.sleep(2)


# ──────────────────────────────────────────────────────────────
#  HAUPTPROGRAMM
# ──────────────────────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info("   Digitaler Bilderrahmen — Start")
    log.info(f"   PIR GPIO Pin:     {GPIO_PIN}")
    log.info(f"   Mikrofon GPIO:    {MIC_GPIO_PIN}  (KY-038 DO)")
    log.info(f"   Aufwärmzeit:      {WARMUP_SEC}s")
    log.info(f"   Timeout:          {TIMEOUT_SEC}s")
    log.info(f"   Mic Cooldown:     {MIC_COOLDOWN}s")
    log.info(f"   Google Drive:     {GDRIVE_REMOTE}")
    log.info(f"   Vollbild:         {VOLLBILD}")
    log.info("=" * 55)

    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)
    os.makedirs(os.path.join(WEB_DIR, "data"), exist_ok=True)    # data/ für JSON-Statusdateien

    status_setzen("warming_up")
    sensor_status_schreiben()

    threads = [
        threading.Thread(target=webserver_thread, name="Webserver",  daemon=True),  # daemon=True: endet automatisch mit Hauptprogramm
        threading.Thread(target=pir_thread,       name="PIR-Sensor", daemon=True),
        threading.Thread(target=mikrofon_thread,  name="Mikrofon",   daemon=True),
        threading.Thread(target=timeout_thread,   name="Timeout",    daemon=True),
        threading.Thread(target=gdrive_thread,    name="GDrive",     daemon=True),
        threading.Thread(target=control_thread,   name="Control",    daemon=True),
    ]

    for t in threads:
        t.start()
        log.info(f"Thread gestartet: {t.name}")

    log.info("Chromium wird geöffnet...")
    browser_starten()

    log.info("Warte auf Aufwärmphase...")
    while not system_ready:
        time.sleep(1)    # Hauptthread wartet bis PIR bereit ist

    log.info("System bereit! Bilderrahmen läuft.")

    try:
        while True:
            time.sleep(1)    # Hauptthread am Leben halten — Threads laufen im Hintergrund
    except KeyboardInterrupt:
        log.info("\nBeendet (Strg+C).")
        status_setzen("sleeping")
        browser_stoppen()
        monitor_aus()
        log.info("Auf Wiedersehen!")


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
