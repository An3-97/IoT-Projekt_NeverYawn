"""
    Programmname: aktor_steuerung.py
    Erstelldatum: 27.05.2025
    Zuletzt bearbeitet: 06.05.2025
    Ersteller: Andrej Kriger
    Programmbeschreibung:
        Steuert einen Servo (z.B. für eine Winke-Bewegung) und einen
        Summer (kurzes Piepen oder dauerhaftes Ein-/Ausschalten) über PWM-Signale.
    Hardware:
        - ESP32-S3-C1
        - SG90 Servo (180°)
        - Summer (passiv, über PWM angesteuert)
"""
import machine
import time
import gc

# --- Konfiguration ---
# Servo
SERVO_FREQUENZ = 50      # PWM-Frequenz für Standard-Servos (in Hz)
SERVO_DUTY_MIN = 26      # PWM-Duty-Wert für 0 Grad (ca. 0.5ms)
SERVO_DUTY_MAX = 128     # PWM-Duty-Wert für 180 Grad (ca. 2.5ms)
SERVO_STANDARD_WINKEL = 90 # Winkel für die Ruheposition

# Summer (Buzzer)
SUMMER_STANDARD_FREQUENZ = 1000 # Frequenz für den Ton (in Hz)
SUMMER_DUTY_AN = 512          # PWM-Duty-Wert für "AN" 
SUMMER_DUTY_AUS = 0           # PWM-Duty-Wert für "AUS"
SUMMER_PIEP_DAUER_MS = 300    # Dauer für einen kurzen Piepton (in Millisekunden)

# --- Modul-Variablen ---
# Diese Variablen speichern den Zustand der Aktoren und Pins
_servo_pwm_objekt = None
_summer_pwm_objekt = None
_ist_stummgeschaltet = False   # Globaler Mute-Status für den Summer
_servo_pin_nr = -1
_summer_pin_nr = -1
_summer_aktuelle_frequenz = SUMMER_STANDARD_FREQUENZ
_summer_ist_dauerhaft_an = False # Status für dauerhaften Betrieb

# --- Interne Hilfsfunktionen ---
def _winkel_zu_duty(winkel):
    """Rechnet einen Winkel (0-180) in einen PWM-Duty-Wert um."""
    # Winkel auf gültigen Bereich begrenzen
    winkel = max(0, min(180, winkel))
    # Lineare Umrechnung
    duty = SERVO_DUTY_MIN + (SERVO_DUTY_MAX - SERVO_DUTY_MIN) * (winkel / 180.0)
    return int(duty)

# --- Öffentliche Funktionen ---
def aktoren_initialisieren(servo_pin_nummer, summer_pin_nummer, summer_frequenz=SUMMER_STANDARD_FREQUENZ):
    """
    Initialisiert die PWM-Ausgänge für Servo und Summer.

    Legende:
        servo_pin_nummer (int): GPIO-Pin für den Servo.
        summer_pin_nummer (int): GPIO-Pin für den Summer.
        summer_frequenz (int, optional): Frequenz für den Summer-Ton.
                                         Standardwert: SUMMER_STANDARD_FREQUENZ.
    """
    global _servo_pwm_objekt, _summer_pwm_objekt, _servo_pin_nr, _summer_pin_nr
    global _summer_aktuelle_frequenz, _summer_ist_dauerhaft_an

    _servo_pin_nr = servo_pin_nummer
    _summer_pin_nr = summer_pin_nummer
    _summer_aktuelle_frequenz = summer_frequenz
    _summer_ist_dauerhaft_an = False # Sicherstellen, dass Status initial aus ist

    print(f"Initialisiere Aktoren: Servo an Pin {_servo_pin_nr}, Summer an Pin {_summer_pin_nr} (Freq: {_summer_aktuelle_frequenz} Hz)")

    # Summer initialisieren
    try:
        summer_pin_obj = machine.Pin(_summer_pin_nr, machine.Pin.OUT) # Pin als Ausgang definieren
        _summer_pwm_objekt = machine.PWM(summer_pin_obj, freq=_summer_aktuelle_frequenz, duty=SUMMER_DUTY_AUS)
        print("Summer (PWM) initialisiert.")
    except Exception as e:
        print(f"FEHLER bei Summer-Initialisierung an Pin {_summer_pin_nr}: {e}")
        _summer_pwm_objekt = None

    # Servo initialisieren
    try:
        servo_pin_obj = machine.Pin(_servo_pin_nr, machine.Pin.OUT) # Pin als Ausgang definieren
        _servo_pwm_objekt = machine.PWM(servo_pin_obj, freq=SERVO_FREQUENZ, duty=0) # Initial Duty 0
        # Servo in Standardposition bringen
        duty_standard = _winkel_zu_duty(SERVO_STANDARD_WINKEL)
        _servo_pwm_objekt.duty(duty_standard)
        time.sleep_ms(500) # Zeit zum Positionieren
        print(f"Servo initialisiert und auf {SERVO_STANDARD_WINKEL} Grad gesetzt.")
    except Exception as e:
        print(f"FEHLER bei Servo-Initialisierung an Pin {_servo_pin_nr}: {e}")
        _servo_pwm_objekt = None

    gc.collect() # Speicherbereinigung

def servo_winkel_setzen(winkel):
     """Setzt den Servo auf einen bestimmten Winkel (0-180 Grad)."""
     global _servo_pwm_objekt
     if _servo_pwm_objekt is None:
         return
     try:
         duty = _winkel_zu_duty(winkel)
         _servo_pwm_objekt.duty(duty)
     except Exception as e:
         print(f"FEHLER beim Setzen des Servo-Winkels: {e}")

def servo_winken(wiederholungen=3, winkel1=45, winkel2=135, pause_ms=400):
    """Lässt den Servo zwischen zwei Winkeln hin und her winken."""
    global _servo_pwm_objekt
    if _servo_pwm_objekt is None:
        return

    print(f"Servo winkt {wiederholungen} mal...")
    try:
        duty1 = _winkel_zu_duty(winkel1)
        duty2 = _winkel_zu_duty(winkel2)
        duty_standard = _winkel_zu_duty(SERVO_STANDARD_WINKEL)

        # Winke-Bewegung durchführen
        for _ in range(wiederholungen):
            _servo_pwm_objekt.duty(duty1)
            time.sleep_ms(pause_ms)
            _servo_pwm_objekt.duty(duty2)
            time.sleep_ms(pause_ms)

        # Zurück zur Standardposition
        _servo_pwm_objekt.duty(duty_standard)
        print("Winken beendet.")
    except Exception as e:
        print(f"FEHLER während des Servo-Winkens: {e}")
        # Versuch, zur Mitte zurückzukehren bei Fehler
        try:
            if _servo_pwm_objekt:
                 _servo_pwm_objekt.duty(_winkel_zu_duty(SERVO_STANDARD_WINKEL))
        except:
            pass # Fehler ignorieren

# --- Summer Funktionen ---
def summer_kurz_piepen(dauer_ms=SUMMER_PIEP_DAUER_MS, frequenz=None, erzwingen=False):
    """
    Aktiviert den Summer für eine kurze, definierte Dauer (Piepton).
    Beachtet den Stummschaltungs-Status, es sei denn 'erzwingen' ist True.
    Verhindert Piepen, wenn der Summer bereits dauerhaft an ist.

    Legende:
        dauer_ms (int, optional): Dauer des Pieptons in Millisekunden.
        frequenz (int, optional): Frequenz des Tons. Standard ist die initialisierte Frequenz.
        erzwingen (bool, optional): Wenn True, wird die Stummschaltung ignoriert.
    """
    global _summer_pwm_objekt, _ist_stummgeschaltet, _summer_aktuelle_frequenz, _summer_ist_dauerhaft_an
    if _summer_pwm_objekt is None: return # Nichts tun, wenn nicht initialisiert
    if _ist_stummgeschaltet and not erzwingen: return # Stummgeschaltet und nicht erzwungen
    if _summer_ist_dauerhaft_an: return # Nicht piepen, wenn schon dauerhaft an

    aktuelle_frequenz = frequenz if frequenz is not None else _summer_aktuelle_frequenz
    print(f"Summer: Kurzer Piep ({dauer_ms}ms, {aktuelle_frequenz} Hz){' (Stumm ignoriert)' if erzwingen else ''}")
    try:
        _summer_pwm_objekt.freq(aktuelle_frequenz)
        _summer_pwm_objekt.duty(SUMMER_DUTY_AN)
        time.sleep_ms(dauer_ms)
        _summer_pwm_objekt.duty(SUMMER_DUTY_AUS)
    except Exception as e:
        print(f"FEHLER beim Summer-Piepen: {e}")
        # Sicherstellen, dass der Summer aus ist
        try:
            if _summer_pwm_objekt: _summer_pwm_objekt.duty(SUMMER_DUTY_AUS)
        except: pass

def summer_starten(frequenz=None, erzwingen=False):
    """
    Schaltet den Summer dauerhaft ein.
    Beachtet den Stummschaltungs-Status, es sei denn 'erzwingen' ist True.

    Legende:
        frequenz (int): Frequenz des Tons. Standard ist die initialisierte Frequenz.
        erzwingen (bool): Wenn True, wird die Stummschaltung ignoriert.
    """
    global _summer_pwm_objekt, _ist_stummgeschaltet, _summer_aktuelle_frequenz, _summer_ist_dauerhaft_an
    if _summer_pwm_objekt is None: return
    if _ist_stummgeschaltet and not erzwingen:
        summer_stoppen() # Sicherstellen, dass er aus ist
        return
    # Wenn schon an und nicht erzwungen, nichts tun
    if _summer_ist_dauerhaft_an and not erzwingen:
        return

    aktuelle_frequenz = frequenz if frequenz is not None else _summer_aktuelle_frequenz
    print(f"Summer: Dauerhaft AN ({aktuelle_frequenz} Hz){' (Stumm ignoriert)' if erzwingen else ''}")
    try:
        _summer_pwm_objekt.freq(aktuelle_frequenz)
        _summer_pwm_objekt.duty(SUMMER_DUTY_AN)
        _summer_ist_dauerhaft_an = True # Status merken
    except Exception as e:
        print(f"FEHLER beim Starten des Summers: {e}")
        _summer_ist_dauerhaft_an = False # Status bei Fehler zurücksetzen

def summer_stoppen():
    """Schaltet den Summer dauerhaft aus."""
    global _summer_pwm_objekt, _summer_ist_dauerhaft_an
    if _summer_pwm_objekt is None: return

    try:
        _summer_pwm_objekt.duty(SUMMER_DUTY_AUS)
    except Exception as e:
        print(f"FEHLER beim Stoppen des Summers: {e}")
    finally:
         _summer_ist_dauerhaft_an = False # Status immer zurücksetzen

def stumm_schalten(status):
    """
    Aktiviert oder deaktiviert die Stummschaltung für den Summer.
    Wenn aktiviert, wird der Summer sofort gestoppt.

    Legende:
        status (bool): True zum Stummschalten, False zum Aufheben.
    """
    global _ist_stummgeschaltet
    _ist_stummgeschaltet = bool(status)
    print(f"Summer Stummschaltung: {'Aktiviert' if _ist_stummgeschaltet else 'Deaktiviert'}")
    # Wenn stummgeschaltet wird, Summer stoppen
    if _ist_stummgeschaltet:
        summer_stoppen()

def ist_stummgeschaltet():
    """Gibt den aktuellen Stummschaltungs-Status zurück (True/False)."""
    global _ist_stummgeschaltet
    return _ist_stummgeschaltet

# --- Aufräumfunktion ---
def aktoren_aufräumen():
    """Gibt die verwendeten PWM-Ressourcen frei."""
    global _servo_pwm_objekt, _summer_pwm_objekt
    print("Räume Aktor-Ressourcen auf...")
    # Servo
    if _servo_pwm_objekt is not None:
        try:
            _servo_pwm_objekt.duty(0) # Signal stoppen
            _servo_pwm_objekt.deinit() # PWM freigeben
            print("Servo PWM deinitialisiert.")
        except Exception as e:
            print(f"FEHLER bei Servo Deinitialisierung: {e}")
        finally:
             _servo_pwm_objekt = None # Referenz entfernen
    # Summer
    if _summer_pwm_objekt is not None:
         try:
             _summer_pwm_objekt.duty(0) # Signal stoppen
             _summer_pwm_objekt.deinit() # PWM freigeben
             print("Summer PWM deinitialisiert.")
         except Exception as e:
             print(f"FEHLER bei Summer Deinitialisierung: {e}")
         finally:
              _summer_pwm_objekt = None # Referenz entfernen
    gc.collect() # Speicherbereinigung
