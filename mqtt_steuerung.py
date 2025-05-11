"""
    Programmname: mqtt_steuerung.py
    Erstelldatum: 02.05.2025
    Zuletzt bearbeitet: 06.05.2025
    Ersteller: Andrej Kriger
    Programmbeschreibung:
        Stellt Funktionen zum Verbinden mit einem MQTT-Broker, zum Senden
        von Nachrichten (Publish) und zum Empfangen von Nachrichten (Subscribe)
        über einen Callback zur Verfügung. Verwendet die umqttsimple Bibliothek.
    Hardware:
        - ESP32-S3-C1
"""

from umqqtsimple import MQTTClient
import ujson
import gc

# --- MQTT Konfiguration ---
MQTT_BROKER_ADRESSE = "192.168.178.56" # IP-Adresse des MQTT Brokers
MQTT_PORT = 1883                      # MQTT Port
mqtt_client_ID = "IoT-NeverYawn"      # ID für MQTT Client
MQTT_KEEP_ALIVE_SEK = 60              # Keep-Alive Intervall in Sekunden

# Topics für dieses Projekt
SENDE_TOPIC = "IoT-NeverYawn/Sensordaten"        # Topic zum Senden von Sensordaten
EMPFANGS_TOPIC = "IoT-NeverYawn/Geraetesteuerung" # Topic zum Empfangen von Steuerbefehlen

# --- Modul-Variablen ---
# Diese Variablen speichern den Zustand des Moduls
mqtt_client = None             # Hält das MQTTClient Objekt der umqttsimple Bibliothek
mqtt_verbunden = False         # Speichert, ob aktuell eine Verbindung besteht
mqtt_benutzer_callback = None  # Speichert die vom Hauptprogramm gesetzte Callback-Funktion

# --- Interne Callback-Funktion ---
def _mqtt_interner_callback(topic, msg):
    """
    Diese Funktion wird von der umqttsimple Bibliothek aufgerufen, wenn eine
    Nachricht auf einem abonnierten Topic empfangen wird.
    Sie ruft dann die Callback-Funktion auf, die im Hauptprogramm
    definiert wurde (mqtt_benutzer_callback).
    """
    global mqtt_benutzer_callback
    if mqtt_benutzer_callback is not None: # Prüfen, ob ein Callback gesetzt wurde
        try:
            # Rufe die Funktion auf, die das Hauptprogramm übergeben hat
            mqtt_benutzer_callback(topic, msg)
        except Exception as e:
            print(f"FEHLER im MQTT Benutzer-Callback: {e}")

# --- Öffentliche Funktionen ---
def mqtt_callback_setzen(benutzer_callback_funktion):
    """
    Setzt die Funktion, die aufgerufen werden soll, wenn eine MQTT-Nachricht
    auf einem abonnierten Topic empfangen wird.

    Legende:
        benutzer_callback_funktion: Die Funktion im Hauptprogramm, die
                                     zwei Argumente (topic_bytes, msg_bytes) erwartet.
    """
    global mqtt_benutzer_callback, mqtt_client, mqtt_verbunden
    mqtt_benutzer_callback = benutzer_callback_funktion
    if mqtt_client is not None and mqtt_verbunden:
        try:
            mqtt_client.set_callback(_mqtt_interner_callback)
        except Exception as e:
            print(f"FEHLER: Konnte Callback nicht im aktiven MQTT-Klienten setzen: {e}")

def mqtt_verbinden():
    """
    Stellt die Verbindung zum MQTT-Broker her und abonniert das
    definierte EMPFANGS_TOPIC. Verwendet die globalen Konfigurationswerte.

    Gibt True bei Erfolg zurück, False bei Fehlern.
    """
    global mqtt_client, mqtt_verbunden

    if mqtt_verbunden:
        return True

    print(f"Verbinde mit MQTT Broker: {MQTT_BROKER_ADRESSE}:{MQTT_PORT} als '{mqtt_client_ID}'...")

    try:
        # Alten Client freigeben (nach Verbindungsabbruch)
        if mqtt_client is not None:
             try:
                  # Versuche, die alte Verbindung sauber zu trennen
                  mqtt_client.disconnect()
             except:
                  pass
        mqtt_client = None
        gc.collect() # Speicherbereinigung

        # Neuen MQTT Client erstellen
        mqtt_client = MQTTClient(client_id=mqtt_client_ID,
                                 server=MQTT_BROKER_ADRESSE,
                                 port=MQTT_PORT,
                                 keepalive=MQTT_KEEP_ALIVE_SEK)

        # Internen Callback setzen
        mqtt_client.set_callback(_mqtt_interner_callback)

        # Verbindung herstellen
        mqtt_client.connect()
        print("MQTT-Verbindung hergestellt.")
        mqtt_verbunden = True # Status auf "verbunden" setzen
        gc.collect() # Speicherbereinigung
        return True

    except OSError as e:
        print(f"FEHLER: MQTT Verbindungsfehler (Netzwerk): {e}")
        mqtt_client = None
        mqtt_verbunden = False
        return False
    except Exception as e:
        print(f"FEHLER: Allgemeiner MQTT Fehler bei Verbindung: {type(e).__name__}: {e}")
        mqtt_client = None
        mqtt_verbunden = False
        return False

def mqtt_senden(payload, topic=SENDE_TOPIC, retain=False, qos=0):
    """
    Veröffentlicht eine Nachricht (payload) auf einem MQTT-Topic.
    das payload (Dictionary) wird automatisch in JSON umgewandelt.

    Legende:
        payload: Die zu sendenden Daten (Dictionary).
        topic: Das MQTT-Topic, auf dem gesendet werden soll (Standard: SENDE_TOPIC).
        retain: Ob der Broker die Nachricht speichern soll (Standard: False).
        qos: Quality of Service Level (Standard: 0).

    Gibt True bei Erfolg zurück, False bei Fehlern.
    """
    global mqtt_client, mqtt_verbunden

    # Nur senden, wenn verbunden
    if not mqtt_verbunden or mqtt_client is None:
        # print("Warnung: MQTT nicht verbunden, Senden nicht möglich.")
        return False

    try:
        # payload in JSON-String umwandeln
        daten_string = ujson.dumps(payload)
        # Nachricht senden
        mqtt_client.publish(topic, daten_string, retain=retain, qos=qos)
        return True

    except OSError as e:
        print(f"FEHLER: MQTT Senden fehlgeschlagen (Netzwerk): {e}")
        # Status und Client zurücksetzen.
        mqtt_verbunden = False
        mqtt_client = None # Erzwingt Neuverbindung im Hauptprogramm
        return False
    except Exception as e:
        print(f"FEHLER: Allgemeiner MQTT Fehler beim Senden: {type(e).__name__}: {e}")
        return False

def mqtt_nachrichten_pruefen():
    """
    Prüft auf eingehende MQTT-Nachrichten. Muss regelmäßig vom Hauptprogramm
    aufgerufen werden, damit Nachrichten empfangen und Callbacks ausgelöst werden.
    """
    global mqtt_client, mqtt_verbunden

    # Nur prüfen, wenn verbunden
    if not mqtt_verbunden or mqtt_client is None:
        return

    try:
        # Ruft die check_msg Methode der umqttsimple Bibliothek auf.
        # Diese prüft nicht-blockierend auf neue Nachrichten.
        # Wenn eine Nachricht da ist, wird intern der Callback (_mqtt_interner_callback)
        # und somit der Benutzer-Callback aufgerufen.
        mqtt_client.check_msg()
    except OSError as e:
        print(f"FEHLER: MQTT Nachrichtenprüfung fehlgeschlagen (Netzwerk): {e}")
        # Status und Client zurücksetzen.
        mqtt_verbunden = False
        mqtt_client = None # Erzwingt Neuverbindung im Hauptprogramm
    except Exception as e:
        print(f"FEHLER: Allgemeiner MQTT Fehler bei Nachrichtenprüfung: {type(e).__name__}: {e}")


def mqtt_ist_verbunden():
    """Gibt zurück, ob aktuell eine Verbindung zum MQTT-Broker besteht."""
    return mqtt_verbunden

def mqtt_trennen():
     """Trennt die MQTT-Verbindung sauber."""
     global mqtt_client, mqtt_verbunden
     if mqtt_client is not None:
          try:
               print("Trenne MQTT-Verbindung...")
               mqtt_client.disconnect()
          except Exception as e:
               print(f"Fehler beim MQTT trennen (ignoriert): {e}")
          finally:
               # Variablen zurücksetzen
               mqtt_client = None
               mqtt_verbunden = False
