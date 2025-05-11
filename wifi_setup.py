"""
    Programmname: wifi_setup.py
    Erstelldatum: 01.05.2025
    Zuletzt bearbeitet: 06.05.2025
    Ersteller: Andrej Kriger
    Programmbeschreibung:
        Stellt Funktionen zur Verfügung, um eine Verbindung zum WLAN herzustellen,
        zu trennen und den Verbindungsstatus zu prüfen.
    Hardware:
        - ESP32-S3-C1
"""

import network
import time

# --- WLAN Zugangsdaten ---
WLAN_SSID = "FRITZ!Box 6591 Cable RK"  
WLAN_PASSWORT = "76309183526677860205" 

# --- Konfiguration ---
WLAN_VERBINDUNGS_TIMEOUT_SEK = 20 # Maximale Wartezeit für Verbindung (in Sekunden)

# --- Interne Modulvariable ---
# Hält das Objekt für das WLAN Station Interface
_wlan_interface = None


# --- Funktionen ---
def wlan_verbinden():
    """
    Aktiviert das WLAN-Interface und versucht, eine Verbindung
    mit den konfigurierten Zugangsdaten herzustellen.

    Gibt True zurück, wenn die Verbindung erfolgreich hergestellt wurde,
    sonst False (bei Fehlern oder Timeout).
    """
    global _wlan_interface

    # Prüfen, ob schon eine Verbindung besteht
    if wlan_ist_verbunden():
        return True

    print(f"Versuche Verbindung mit WLAN '{WLAN_SSID}'...")

    # WLAN-Interface initialisieren, falls noch nicht geschehen
    if _wlan_interface is None:
        try:
            _wlan_interface = network.WLAN(network.STA_IF)
        except Exception as e:
            print(f"FEHLER: WLAN-Interface konnte nicht erstellt werden: {e}")
            return False

    # WLAN-Interface aktivieren, falls nicht aktiv
    if not _wlan_interface.active():
        try:
            _wlan_interface.active(True)
            # Kurze Pause nach Aktivierung
            time.sleep(1)
            print("WLAN-Interface aktiviert.")
        except Exception as e:
            print(f"FEHLER: WLAN-Interface konnte nicht aktiviert werden: {e}")
            return False

    # Verbindungsversuch starten
    try:
        _wlan_interface.connect(WLAN_SSID, WLAN_PASSWORT)
        print("Verbindungsaufbau gestartet...")
    except Exception as e:
        print(f"FEHLER: Verbindungsaufbau fehlgeschlagen: {e}")
        return False

    # Warten auf erfolgreiche Verbindung (mit Timeout)
    start_zeit = time.time()
    while not _wlan_interface.isconnected():
        # Prüfen, ob Timeout überschritten wurde
        if time.time() - start_zeit > WLAN_VERBINDUNGS_TIMEOUT_SEK:
            print(f"FEHLER: WLAN-Verbindung Timeout ({WLAN_VERBINDUNGS_TIMEOUT_SEK}s).")
            # Verbindung aktiv abbrechen und Interface deaktivieren
            try:
                 _wlan_interface.disconnect()
                 _wlan_interface.active(False)
            except Exception as e_disconnect:
                 print(f"Fehler beim Deaktivieren nach Timeout: {e_disconnect}")
            return False

        # Kurze Pause und Punkt ausgeben
        print(".", end="") # Zeigt an, dass gewartet wird
        time.sleep(1)

    # Wenn die Schleife beendet wurde, ist die Verbindung erfolgreich
    print("\nWLAN verbunden!")
    try:
        # IP-Konfiguration ausgeben
        ip_config = _wlan_interface.ifconfig()
        print(f"IP Konfiguration: IP={ip_config[0]}, Subnetz={ip_config[1]}, Gateway={ip_config[2]}, DNS={ip_config[3]}")
    except Exception as e:
         print(f"Info: IP-Konfiguration konnte nicht gelesen werden: {e}")
    return True

def wlan_trennen():
    """Trennt die aktuelle WLAN-Verbindung und deaktiviert das Interface."""
    global _wlan_interface

    if _wlan_interface is not None and _wlan_interface.active():
        try:
            if _wlan_interface.isconnected():
                print("Trenne WLAN-Verbindung...")
                _wlan_interface.disconnect()
            print("Deaktiviere WLAN-Interface...")
            _wlan_interface.active(False)
            print("WLAN getrennt und deaktiviert.")
        except Exception as e:
            print(f"FEHLER beim Trennen/Deaktivieren des WLANs: {e}")
    else:
        pass

def wlan_ist_verbunden():
    """Prüft, ob eine aktive WLAN-Verbindung besteht."""
    global _wlan_interface
    # Prüft ob das Objekt existiert, aktiv ist UND verbunden ist
    if _wlan_interface is not None and _wlan_interface.active() and _wlan_interface.isconnected():
        return True
    else:
        return False
