"""
    Programmname: main.py
    Erstelldatum: 01.04.2025
    Zuletzt bearbeitet: 07.05.2025
    Ersteller: Andrej Kriger
    Programmbeschreibung:
        Dies ist das Hauptprogramm des IoT-Projekts "Never-Yawn". Es importiert
        und initialisiert die verschiedenen Module (WLAN, MQTT, Sensorik,
        Display, Aktoren), verwaltet die Netzwerkverbindungen, liest periodisch
        Sensordaten aus, prüft diese gegen konfigurierbare Schwellenwerte,
        löst Alarme aus (visuell, akustisch), aktualisiert das Display,
        sendet Daten an einen MQTT-Broker und empfängt Steuerungs- sowie
        Konfigurationsbefehle über MQTT.
    Hardware:
        - ESP32-S3-C1
"""
import time
import gc
import ujson
from machine import Pin, Timer

# --- Eigene Module importieren ---
import wifi_setup          # Modul für WLAN-Verbindung
import mqtt_steuerung      # Modul für MQTT-Kommunikation
import sensorik            # Modul zum Auslesen der Sensoren
import display_steuerung   # Modul zur Ansteuerung des Displays
import aktor_steuerung     # Modul zur Ansteuerung der Aktoren


# --- Globale Konfiguration ---
# Pin-Belegung
SERVO_PIN = 21      # Pin für Servo
SUMMER_PIN = 47     # Pin für den Summer (Buzzer)

# Zeitintervalle
SENSOR_LESEINTERVALL_SEK = 2      # Wie oft Sensoren lesen/senden (in Sekunden)
WLAN_NEUVERBINDUNG_WARTEZEIT_SEK = 15 # Wartezeit vor WLAN Reconnect-Versuch
MQTT_NEUVERBINDUNG_WARTEZEIT_SEK = 15 # Wartezeit vor MQTT Reconnect-Versuch
HAUPTSCHLEIFE_PAUSE_MS = 200      # Kurze Pause in der Hauptschleife (in Millisekunden)

# Standard-Schwellwerte (werden von MQTT überschrieben)
STANDARD_TEMP_SCHWELLE = 30.0
STANDARD_FEUCHTE_SCHWELLE = 60.0
STANDARD_CO2_SCHWELLE = 1500
STANDARD_VOC_SCHWELLE = 1000
STANDARD_CO2_KRITISCH_SCHWELLE = 2500 # Kritischer Wert

# Alarm-Logik Konfiguration
NORMAL_ALARM_SPERRE_SEK = 300     # Cooldown für normalen Alarm (Sekunden)
NORMAL_ALARM_AUSLOESE_ZAEHLER = 2 # Anzahl Messungen über Grenzwert für normalen Alarm

# MQTT Topic für Schwellwerte
MQTT_SCHWELLE_TOPIC = "IoT-NeverYawn/Schwellwerte"

# --- Globale Variablen ---
letzte_sensorlesung_zeit = 0
kritischer_alarm_aktiv = False    # kritische Dauer-Alarm aktiv?
normal_alarm_sperre_bis = 0       # Zeitstempel, bis wann der nächste normale Alarm unterdrückt wird
normal_alarm_zaehler = 0          # Zähler für aufeinanderfolgende Grenzwertüberschreitungen

# Aktuelle Schwellwerte (initialisiert mit Standardwerten)
aktuelle_temp_schwelle = STANDARD_TEMP_SCHWELLE
aktuelle_feuchte_schwelle = STANDARD_FEUCHTE_SCHWELLE
aktuelle_co2_schwelle = STANDARD_CO2_SCHWELLE
aktuelle_voc_schwelle = STANDARD_VOC_SCHWELLE
aktuelle_co2_kritisch_schwelle = STANDARD_CO2_KRITISCH_SCHWELLE

# --- Initialisierung ---
print("Initialisiere Module...")

bildschirm = display_steuerung.DisplaySteuerung()
bildschirm.setup()
print("Display initialisiert.")

aktor_steuerung.aktoren_initialisieren(SERVO_PIN, SUMMER_PIN)
print("Aktoren initialisiert.")

print("Sensorik initialisiert.") # wird beim Import initialisiert

# --- MQTT Callback Funktion ---
def mqtt_befehl_empfangen(topic_bytes, msg_bytes):
    """Verarbeitet eingehende MQTT-Nachrichten (Steuerung & Konfiguration)."""
    global kritischer_alarm_aktiv, normal_alarm_sperre_bis
    # Zugriff auf globale Schwellwert-Variablen zum Aktualisieren
    global aktuelle_temp_schwelle, aktuelle_feuchte_schwelle, aktuelle_co2_schwelle
    global aktuelle_voc_schwelle, aktuelle_co2_kritisch_schwelle

    try:
        topic = topic_bytes.decode('utf-8')
        print(f"MQTT empfangen: Topic='{topic}'") # Info über empfangene Nachricht

        # --- Konfigurations-Topic für Schwellwerte ---
        if topic == MQTT_SCHWELLE_TOPIC:
            try:
                daten = ujson.loads(msg_bytes)
                print(f"Empfangene Konfiguration: {daten}")

                # Schwellwerte aktualisieren (mit Prüfung)
                neue_temp = daten.get('schwelle_temp') # aus Node-RED
                if isinstance(neue_temp, (int, float)):
                    aktuelle_temp_schwelle = float(neue_temp)
                    #print(f"  -> Temp Schwelle: {aktuelle_temp_schwelle}")

                neue_feuchte = daten.get('schwelle_hum') # Key aus Node-RED
                if isinstance(neue_feuchte, (int, float)) and 0 <= neue_feuchte <= 100:
                    aktuelle_feuchte_schwelle = float(neue_feuchte)
                    #print(f"  -> Feuchte Schwelle: {aktuelle_feuchte_schwelle}")

                neue_co2 = daten.get('schwelle_CO2') # aus Node-RED
                if isinstance(neue_co2, (int, float)) and neue_co2 > 0:
                    aktuelle_co2_schwelle = int(neue_co2)
                    #print(f"  -> CO2 Schwelle: {aktuelle_co2_schwelle}")

                neue_voc = daten.get('schwelle_VOC') # aus Node-RED
                if isinstance(neue_voc, (int, float)) and neue_voc >= 0:
                    aktuelle_voc_schwelle = int(neue_voc)
                    #print(f"  -> VOC Schwelle: {aktuelle_voc_schwelle}")

            except Exception as e:
                print(f"Fehler beim Verarbeiten der Schwelle-Nachricht: {e}")
            return 

        # --- Steuerungs-Topic ---
        elif topic == mqtt_steuerung.EMPFANGS_TOPIC:
            daten = ujson.loads(msg_bytes)
            befehl = daten.get('command')
            status = daten.get('status')
            aktion = daten.get('action')

            if befehl == "MUTE":
                mute_aktiv = (status == "ON")
                aktor_steuerung.stumm_schalten(mute_aktiv)
                if mute_aktiv:
                    kritischer_alarm_aktiv = False
            elif befehl == "FLAG" and aktion == "WAVE":
                print("Aktion: Servo winken (MQTT)")
                aktor_steuerung.servo_winken(wiederholungen=3)
            elif befehl == "BUZZER":
                if status == "ON":
                    print("Aktion: Summer AN (MQTT)")
                    aktor_steuerung.summer_starten()
                elif status == "OFF":
                    print("Aktion: Summer AUS (MQTT)")
                    aktor_steuerung.summer_stoppen()
                    kritischer_alarm_aktiv = False

    except Exception as e:
        print(f"Fehler im MQTT Callback: {e}")

# --- MQTT Verbindungsfunktion ---
def mqtt_verbinden_und_abonnieren():
    """Stellt MQTT-Verbindung her und abonniert Steuerungs- & Konfig-Topics."""
    global mqtt_ok # globales Flag für Verbindungsstatus
    print("Versuche MQTT zu verbinden...")
    if mqtt_steuerung.mqtt_verbinden():
         try:
              # Steuerungs-Topic aus Modul abonnieren
              print(f"Abonniere Steuerung: {mqtt_steuerung.EMPFANGS_TOPIC}")
              mqtt_steuerung.mqtt_client.subscribe(mqtt_steuerung.EMPFANGS_TOPIC)

              # Konfigurations-Topic abonnieren
              print(f"Abonniere Konfiguration: {MQTT_SCHWELLE_TOPIC}")
              mqtt_steuerung.mqtt_client.subscribe(MQTT_SCHWELLE_TOPIC)

              mqtt_ok = True
              print("MQTT verbunden und Topics abonniert.")
              return True
         except Exception as e:
              print(f"Fehler beim Abonnieren der MQTT Topics: {e}")
              # Bei Fehler Verbindung wieder trennen
              try: mqtt_steuerung.mqtt_trennen()
              except: pass
              mqtt_ok = False
              return False
    else:
         mqtt_ok = False
         return False

# MQTT Callback Funktion setzen
try:
    mqtt_steuerung.mqtt_callback_setzen(mqtt_befehl_empfangen)
    print("MQTT Callback Funktion gesetzt.")
except Exception as e:
    print(f"FEHLER beim Setzen des MQTT Callbacks: {e}")

# --- Sensor-Verarbeitungsfunktion (wird vom Timer aufgerufen) ---
def sensoren_lesen_verarbeiten_senden(timer_obj=None):
    """Liest Sensoren, prüft Grenzwerte, aktualisiert Display, sendet MQTT."""
    global letzte_sensorlesung_zeit, kritischer_alarm_aktiv
    global normal_alarm_sperre_bis, normal_alarm_zaehler
    # Zugriff auf aktuelle Schwellwerte
    global aktuelle_temp_schwelle, aktuelle_feuchte_schwelle, aktuelle_co2_schwelle
    global aktuelle_voc_schwelle, aktuelle_co2_kritisch_schwelle

    aktuelle_zeit = time.time()
    letzte_sensorlesung_zeit = aktuelle_zeit

    try:
        # --- Sensoren lesen ---
        temp = sensorik.lese_temperatur()
        feuchte = sensorik.lese_feuchtigkeit()
        co2 = sensorik.lese_co2()
        voc = sensorik.lese_voc()

        if temp == -99.9 or feuchte == -1:
             print("WARNUNG: Ungültige AHT10 Werte, überspringe Zyklus.")
             return

        #print(f"Werte: T={temp:.1f}C, H={feuchte:.1f}%, CO2={co2}ppm, VOC={voc}ppb")

        # --- Grenzwerte prüfen ---
        ist_temp_alarm = temp > aktuelle_temp_schwelle
        ist_feuchte_alarm = feuchte > aktuelle_feuchte_schwelle
        ist_co2_alarm = co2 > aktuelle_co2_schwelle
        ist_voc_alarm = voc > aktuelle_voc_schwelle
        ist_co2_kritisch = co2 > aktuelle_co2_kritisch_schwelle

        soll_normal_alarm = ist_temp_alarm or ist_feuchte_alarm or ist_co2_alarm or ist_voc_alarm

        # --- Display aktualisieren ---
        if bildschirm:
            try:
                bildschirm.display_aktualisieren(
                    temp, feuchte, co2, voc,
                    ist_temp_alarm, ist_feuchte_alarm, ist_co2_alarm, ist_voc_alarm,
                    aktuelle_temp_schwelle, aktuelle_feuchte_schwelle,
                    aktuelle_co2_schwelle, aktuelle_voc_schwelle
                )
            except Exception as e: print(f"Fehler beim Display Update: {e}")

        # --- Alarm Logik ---
        # 1. Kritischer CO2-Alarm
        if ist_co2_kritisch:
            aktor_steuerung.summer_starten(erzwingen=True) # Summer AN (ignoriert Mute)
            if not kritischer_alarm_aktiv:
                print("!!! KRITISCHER CO2 ALARM !!!")
                kritischer_alarm_aktiv = True
                normal_alarm_zaehler = 0
                normal_alarm_sperre_bis = 0
                if bildschirm: bildschirm.backlight_einschalten() # Display an
        else:
            if kritischer_alarm_aktiv:
                print("Kritischer CO2-Alarm beendet.")
                aktor_steuerung.summer_stoppen() # Summer AUS
                kritischer_alarm_aktiv = False
                if soll_normal_alarm:
                     print("Werte noch erhöht, starte normalen Alarm Cooldown.")
                     normal_alarm_sperre_bis = aktuelle_zeit + NORMAL_ALARM_SPERRE_SEK
                     normal_alarm_zaehler = 0

        # 2. Normaler Alarm
        if not kritischer_alarm_aktiv:
            if soll_normal_alarm:
                normal_alarm_zaehler += 1
                if normal_alarm_zaehler >= NORMAL_ALARM_AUSLOESE_ZAEHLER and \
                   aktuelle_zeit > normal_alarm_sperre_bis:
                     print(f"!!! Normaler Alarm (>= {NORMAL_ALARM_AUSLOESE_ZAEHLER}x, nach Cooldown) !!!")
                     aktor_steuerung.summer_kurz_piepen() # Kurzer Piep (respektiert Mute)
                     aktor_steuerung.servo_winken(wiederholungen=3) # Servo winken
                     if bildschirm: bildschirm.backlight_einschalten() # Display an
                     normal_alarm_sperre_bis = aktuelle_zeit + NORMAL_ALARM_SPERRE_SEK
                     normal_alarm_zaehler = 0
            else:
                 if normal_alarm_zaehler > 0: normal_alarm_zaehler = 0
                 if normal_alarm_sperre_bis > 0: normal_alarm_sperre_bis = 0

        # --- Daten via MQTT senden ---
        if mqtt_steuerung.mqtt_ist_verbunden():
            temp_zustand = 1 if ist_temp_alarm else 0
            feuchte_zustand = 1 if ist_feuchte_alarm else 0
            co2_zustand = 2 if ist_co2_kritisch else (1 if ist_co2_alarm else 0)
            voc_zustand = 1 if ist_voc_alarm else 0
            daten = {
                "Temperatur": temp, "Temperatur_Status": temp_zustand,
                "Luftfeuchtigkeit": feuchte, "Luftfeuchtigkeit_Status": feuchte_zustand,
                "CO2": co2, "CO2_Status": co2_zustand,
                "VOC": voc, "VOC_Status": voc_zustand
            }
            mqtt_steuerung.mqtt_senden(payload=daten) # Senden

    except Exception as e:
        print(f"FEHLER in Sensorverarbeitung: {e}")

# --- Programmstart ---
print("--- NeverYawn IoT Start ---")

# WLAN verbinden
print("Verbinde WLAN...")
wlan_ok = wifi_setup.wlan_verbinden()

# MQTT verbinden (nur wenn WLAN OK)
mqtt_ok = False
if wlan_ok:
    mqtt_ok = mqtt_verbinden_und_abonnieren()
else:
    print("WLAN-Verbindung fehlgeschlagen!")

# Timer für Sensorablesung starten
try:
    sensor_zeitgeber = Timer(0)
    sensor_zeitgeber.init(period=SENSOR_LESEINTERVALL_SEK * 1000,
                          mode=Timer.PERIODIC,
                          callback=sensoren_lesen_verarbeiten_senden)
    print(f"Sensor-Timer gestartet (Intervall: {SENSOR_LESEINTERVALL_SEK}s).")
except Exception as e:
    print(f"FEHLER beim Starten des Sensor-Timers: {e}")

# --- Hauptschleife ---
print("Starte Hauptschleife...")
try:
    while True:
        # --- Verbindungsmanagement ---
        if not wifi_setup.wlan_ist_verbunden():
            print(f"WLAN nicht verbunden. Reconnect in {WLAN_NEUVERBINDUNG_WARTEZEIT_SEK}s...")
            if mqtt_ok:
                 try: mqtt_steuerung.mqtt_trennen()
                 except: pass
                 mqtt_ok = False
            time.sleep(WLAN_NEUVERBINDUNG_WARTEZEIT_SEK)
            wlan_ok = wifi_setup.wlan_verbinden()
            if wlan_ok: mqtt_ok = False # Erneut versuchen MQTT zu verbinden

        elif wlan_ok and not mqtt_ok:
            print(f"MQTT nicht verbunden. Reconnect in {MQTT_NEUVERBINDUNG_WARTEZEIT_SEK}s...")
            time.sleep(MQTT_NEUVERBINDUNG_WARTEZEIT_SEK)
            mqtt_ok = mqtt_verbinden_und_abonnieren()

        # --- Eingehende MQTT Nachrichten prüfen ---
        if mqtt_ok:
            try:
                mqtt_steuerung.mqtt_nachrichten_pruefen()
                if not mqtt_steuerung.mqtt_ist_verbunden():
                    mqtt_ok = False
            except Exception as e:
                 print(f"Fehler bei MQTT Nachrichtenprüfung: {e}")
                 mqtt_ok = False
                 try: mqtt_steuerung.mqtt_trennen()
                 except: pass

        # --- Kurze Pause ---
        time.sleep_ms(HAUPTSCHLEIFE_PAUSE_MS)

except Exception as e:
    print(f"Unerwarteter Fehler in Hauptschleife: {e}")