"""
    Programmname: sensorik.py
    Erstelldatum: 01.04.2025
    Zuletzt bearbeitet: 04.05.2025
    Ersteller: Andrej Kriger
    Programmbeschreibung:
        Liest die Messwerte der Sensoren AHT10 (Temperatur, Feuchtigkeit)
        und CCS811 (CO2, VOC) über den I2C-Bus aus.
    Hardware:
        - ESP32-S3-C1
        - AHT10 Sensor (I2C Adresse 0x38)
        - CCS811 Sensor (I2C Adresse 0x5A oder 0x5B)
            - WAKE Pin des CCS811 liegt auf GND für Dauerbetrieb.
        - Pin-Belegung:
            - SCL: GPIO 15
            - SDA: GPIO 16
            - VCC (beide): 3.3V
            - GND (beide): GND
"""

from machine import Pin, SoftI2C
from time import sleep
import gc

# Sensor-Bibliotheken importieren
from aht10 import AHT10
from ccs811 import CCS811



# --- Globale Konfiguration ---
I2C_SCL_PIN = 15 # Pin für I2C Clock
I2C_SDA_PIN = 16 # Pin für I2C Data
I2C_FREQUENZ = 100000 # I2C Frequenz in Hz (100kHz Standard)
I2C_TIMEOUT_US = 50000 # I2C Timeout in Mikrosekunden (50ms)

# --- Globale Variablen ---
# Sensor-Objekte (werden bei Initialisierung erstellt)
_sensor_aht10 = None
_sensor_ccs = None

# Zwischenspeicher für die letzten gültigen CCS811-Werte
_letzter_co2_wert = 400 # Startwert
_letzter_voc_wert = 0   # Startwert

# --- Initialisierung ---
# Wird automatisch beim Import des Moduls ausgeführt

print("Initialisiere Sensorik...")
try:
    # I2C Bus erstellen
    print(f"Initialisiere I2C: SCL={I2C_SCL_PIN}, SDA={I2C_SDA_PIN}, Freq={I2C_FREQUENZ}")
    i2c_bus = SoftI2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=I2C_FREQUENZ, timeout=I2C_TIMEOUT_US)

    # I2C Scan zur Diagnose
    print("Suche nach I2C Geräten...")
    gefundene_geraete = i2c_bus.scan()
    if not gefundene_geraete:
        print("WARNUNG: Keine I2C Geräte gefunden!")
    else:
        print("Gefundene I2C Adressen (dez):", gefundene_geraete)
        # print("Gefundene I2C Adressen (hex):", [hex(g) for g in gefundene_geraete])

    # AHT10 Sensor initialisieren (Adresse 0x38 = 56 dez)
    if 56 in gefundene_geraete:
        try:
             print("Initialisiere AHT10...")
             _sensor_aht10 = AHT10(i2c_bus)
             print("AHT10 initialisiert.")
        except Exception as e_aht:
             print(f"FEHLER bei AHT10 Initialisierung: {e_aht}")
             _sensor_aht10 = None # Sicherstellen, dass Objekt None ist bei Fehler
    else:
        print("FEHLER: AHT10 (Adresse 56) nicht gefunden!")

    # CCS811 Sensor initialisieren (Adresse 0x5A=90 oder 0x5B=91 dez)
    ccs_adresse = -1
    if 90 in gefundene_geraete: ccs_adresse = 90
    elif 91 in gefundene_geraete: ccs_adresse = 91

    if ccs_adresse != -1:
        try:
            print(f"Initialisiere CCS811 (Adresse {ccs_adresse})...")
            _sensor_ccs = CCS811(i2c=i2c_bus, addr=ccs_adresse)
            # Kurze Pause, damit der Sensor bereit ist
            sleep(1)
            print("CCS811 initialisiert.")
        except ValueError as e_ccs_val:
             # Spezifischer Fehler aus der CCS811 Bibliothek
             print(f"FEHLER bei CCS811 Initialisierung: {e_ccs_val}")
             _sensor_ccs = None
        except Exception as e_ccs:
             print(f"Allgemeiner FEHLER bei CCS811 Initialisierung: {e_ccs}")
             _sensor_ccs = None
    else:
        print("FEHLER: CCS811 (Adresse 90 oder 91) nicht gefunden!")

except Exception as e_i2c:
    print(f"FEHLER bei I2C Initialisierung: {e_i2c}")

# --- Sensor-Lese-Funktionen ---
def lese_feuchtigkeit():
    """Liest die aktuelle Luftfeuchtigkeit vom AHT10 Sensor."""
    if _sensor_aht10 is not None:
        try:
            feuchte = _sensor_aht10.humidity()
            # Einfache Prüfung auf gültigen Bereich
            if 0 <= feuchte <= 100:
                 return round(feuchte, 1)
            else:
                 return -1
        except Exception as e:
            print(f"FEHLER beim Lesen der Feuchtigkeit: {e}")
            return -1 
    else:
        # Sensor nicht verfügbar
        return -1 # Fehlercode zurückgeben

def lese_temperatur():
    """Liest die aktuelle Temperatur vom AHT10 Sensor."""
    if _sensor_aht10 is not None:
        try:
            temperatur = _sensor_aht10.temperature()
            # Einfache Prüfung auf gültigen Bereich
            if -40 <= temperatur <= 85: # Bereich für AHT10
                return round(temperatur, 1)
            else:
                return -99.9
        except Exception as e:
            print(f"FEHLER beim Lesen der Temperatur: {e}")
            return -99.9
    else:
        # Sensor nicht verfügbar
        return -99.9 # Fehlercode zurückgeben

def _aktualisiere_ccs_daten():
    """
    Interne Funktion: Prüft, ob neue Daten vom CCS811 Sensor verfügbar sind
    und aktualisiert die globalen Zwischenspeicher (_letzter_co2_wert, _letzter_voc_wert).
    """
    global _letzter_co2_wert, _letzter_voc_wert
    if _sensor_ccs is not None:
        try:
            # Prüfen, ob der Sensor neue Daten bereitstellt
            if _sensor_ccs.data_ready():
                neuer_co2 = _sensor_ccs.eCO2
                neuer_voc = _sensor_ccs.tVOC

                # Prüfen ob die gelesenen Werte realistisch sind
                # (CCS811 gibt manchmal unrealistische Werte zurück)
                if 400 <= neuer_co2 <= 8000 and 0 <= neuer_voc:
                    _letzter_co2_wert = neuer_co2
                    _letzter_voc_wert = neuer_voc

        except Exception as e:
            print(f"FEHLER beim Lesen der CCS811 Daten: {e}")


def lese_co2():
    """
    Gibt den zuletzt gültigen CO2-Wert zurück.
    Ruft intern die Funktion zur Aktualisierung der CCS-Daten auf.
    """
    _aktualisiere_ccs_daten() # Prüfen, ob neue Werte verfügbar sind
    return _letzter_co2_wert

def lese_voc():
    """
    Gibt den zuletzt bekannten VOC-Wert zurück.
    """
    # _aktualisiere_ccs_daten() wurde bereits durch lese_co2() aufgerufen.
    return _letzter_voc_wert

def fuehre_gc_aus():
    """Führt den Garbage Collector zur Speicherbereinigung aus."""
    gc.collect()
