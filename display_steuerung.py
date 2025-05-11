"""
    Programmname: display_steuerung.py
    Erstelldatum: 22.04.2025
    Zuletzt bearbeitet: 04.05.2025
    Ersteller: Andrej Kriger
    Programmbeschreibung:
        Steuert das TFT-Display (ILI9341). Zeigt den Titel, Sensorwerte
        (farbig je nach Alarmstatus), die aktuellen Schwellwerte und den
        Verbindungsstatus (WLAN/MQTT) an. Aktualisiert nur geänderte
        Bereiche des Displays. Schaltet die Hintergrundbeleuchtung bei
        Berührung oder bei einem Alarm für eine bestimmte Zeit ein.
    Hardware:
        - ESP32-S3-C1
        - 2.8" TFT Touch-Display (ILI9341, 320x240)
"""

from machine import Pin, SPI, Timer
import time
import gc

# Display-Treiber und Fonts
from ili934xnew import ILI9341, color565
import fonts.roboto21x24 # Großer Font für Werte
import glcdfont          # Kleiner Standardfont für Rest

# Module für Statusabfrage
import wifi_setup        
import mqtt_steuerung    



# --- Pin-Belegung ---
DISPLAY_SPI_ID = 1
DISPLAY_SCK_PIN = 36
DISPLAY_MOSI_PIN = 35
DISPLAY_CS_PIN = 6
DISPLAY_DC_PIN = 5
DISPLAY_RST_PIN = 4
DISPLAY_BL_PIN = 9  # Backlight Pin
TOUCH_IRQ_PIN = 8   # Touch Interrupt Pin

# --- Display-Konstanten ---
DISPLAY_BREITE = 320
DISPLAY_HOEHE = 240
DISPLAY_ROTATION = 1

# --- Farben (RGB565 Format) ---
WEISS = color565(255, 255, 255)
SCHWARZ = color565(0, 0, 0)
ROT = color565(255, 0, 0)
DUNKELGRUEN = color565(0, 180, 0) # lesbares Grün
GRAU = color565(128, 128, 128) # Für Statuszeile
DUNKELGRAU = color565(80, 80, 80) # Für Schwellwerte

# --- Timing ---
BACKLIGHT_TIMEOUT_MS = 15000 # 15 Sekunden

# --- Layout Konstanten ---
RANDABSTAND = 5
TITEL_Y = 5
WERTEBEREICH_BREITE = 95    # Breite für Sensorwerte & Schwellwerte
STATUSBEREICH_BREITE = DISPLAY_BREITE - 4 * RANDABSTAND # Breite für Statuszeile

# --- Display Steuerungs Klasse ---
class DisplaySteuerung:
    """ Klasse zur Verwaltung und Aktualisierung des Displays. """

    def __init__(self):
        """ Initialisiert die Hardware (Pins, SPI) und das Display-Objekt. """
        # Pin-Objekte erstellen
        self.pin_backlight = Pin(DISPLAY_BL_PIN, Pin.OUT)
        self.pin_reset = Pin(DISPLAY_RST_PIN, Pin.OUT)
        self.pin_dc = Pin(DISPLAY_DC_PIN, Pin.OUT)
        self.pin_touch_irq = Pin(TOUCH_IRQ_PIN, Pin.IN, Pin.PULL_UP)

        # SPI-Bus initialisieren
        try:
            self.spi = SPI(DISPLAY_SPI_ID, baudrate=40000000, polarity=0, phase=0,
                           sck=Pin(DISPLAY_SCK_PIN), mosi=Pin(DISPLAY_MOSI_PIN))
        except Exception as e:
            print(f"FEHLER: SPI-Initialisierung fehlgeschlagen: {e}")
            raise SystemExit("SPI Fehler")

        # Display-Treiber initialisieren
        try:
            self.display = ILI9341(self.spi, cs=Pin(DISPLAY_CS_PIN), dc=self.pin_dc,
                                   rst=self.pin_reset, w=DISPLAY_BREITE, h=DISPLAY_HOEHE,
                                   r=DISPLAY_ROTATION)
        except Exception as e:
            print(f"FEHLER: Display-Treiber konnte nicht initialisiert werden: {e}")
            raise SystemExit("Display Fehler")

        # Fonts laden
        self.grosser_font = fonts.roboto21x24
        self.kleiner_font = glcdfont
        try:
            self.display.set_font(self.grosser_font)
            print("Großen Font initial gesetzt.")
        except Exception as e:
            print(f"Fehler beim Setzen des großen Fonts: {e}")
            # Fallback auf kleinen Font, falls großer nicht geht
            try: self.display.set_font(self.kleiner_font)
            except: print("FEHLER: Konnte keinen Font setzen!")

        # Timer für Backlight-Timeout
        self.backlight_timer = Timer(1) # Timer ID 1 verwenden
        self.backlight_aktiv = False    # Status der Hintergrundbeleuchtung

        # Variablen zum Speichern der zuletzt angezeigten Werte/Status
        # Wird benötigt, um nur Änderungen neu zu zeichnen
        self._letzter_temp_wert_str = None
        self._letzter_feuchte_wert_str = None
        self._letzter_co2_wert_str = None
        self._letzter_voc_wert_str = None
        self._letzte_temp_farbe = None
        self._letzte_feuchte_farbe = None
        self._letzte_co2_farbe = None
        self._letzte_voc_farbe = None
        self._letzter_status_str = None
        self._letzter_temp_schwelle_str = None
        self._letzte_feuchte_schwelle_str = None
        self._letzte_co2_schwelle_str = None
        self._letzte_voc_schwelle_str = None

        # Koordinaten für die verschiedenen Display-Bereiche
        self._wert_koordinaten = {}      # Für Sensorwerte
        self._schwelle_koordinaten = {}  # Für Schwellwerte
        self._status_koordinaten = None  # Für Statuszeile
        self._status_zeilenhoehe = 0     # Höhe der Statuszeile

    def _display_initialisieren(self):
        """ Löscht das Display, schaltet Backlight aus, zeichnet statische Elemente. """
        self.display.erase()
        self.pin_backlight.off()
        self.backlight_aktiv = False
        print("Display initialisiert, Backlight aus.")
        self._statische_elemente_zeichnen() # Statische Elemente einmal zeichnen

    def _statische_elemente_zeichnen(self):
        """ Zeichnet den Titel und die Labels einmalig und speichert Koordinaten. """
        print("Zeichne statische Display-Elemente...")
        aktuelle_y = TITEL_Y
        self.display.erase() # Sicherstellen, dass der Hintergrund sauber ist

        # Reset der Koordinaten und gespeicherten Werte
        self._wert_koordinaten = {}
        self._schwelle_koordinaten = {}
        self._status_koordinaten = None
        self._letzter_temp_wert_str = None; self._letzte_temp_farbe = None; self._letzter_temp_schwelle_str = None
        self._letzter_feuchte_wert_str = None; self._letzte_feuchte_farbe = None; self._letzte_feuchte_schwelle_str = None
        self._letzter_co2_wert_str = None; self._letzte_co2_farbe = None; self._letzte_co2_schwelle_str = None
        self._letzter_voc_wert_str = None; self._letzte_voc_farbe = None; self._letzte_voc_schwelle_str = None
        self._letzter_status_str = None

        # --- Titel ---
        try:
            self.display.set_font(self.kleiner_font)
            titel_text = "NeverYawn"
            titel_breite = self.kleiner_font.get_width(titel_text)
            titel_x = (DISPLAY_BREITE - titel_breite) // 2 # Zentriert
            self.display.set_pos(titel_x, aktuelle_y)
            self.display.set_color(WEISS, SCHWARZ)
            self.display.write(titel_text)
            aktuelle_y += self.kleiner_font.height() + RANDABSTAND * 2
        except Exception as e:
            print(f"Fehler beim Zeichnen des Titels: {e}")
            aktuelle_y += 15 # Fallback Abstand

        # --- Sensor-Labels und Koordinaten ---
        try:
            label_x = RANDABSTAND * 2
            wert_x = DISPLAY_BREITE - RANDABSTAND * 2 - WERTEBEREICH_BREITE # Rechtsbündig
            labels_y_start = aktuelle_y + RANDABSTAND

            # Fonts und Höhen bestimmen
            self.display.set_font(self.grosser_font)
            gross_font_h = self.display._font.height()
            self.display.set_font(self.kleiner_font)
            klein_font_h = self.display._font.height()
            zeilenhoehe_gesamt = gross_font_h + klein_font_h + RANDABSTAND

            # Temperatur Label + Koordinaten speichern
            self.display.set_font(self.grosser_font)
            self.display.set_color(WEISS, SCHWARZ)
            self.display.set_pos(label_x, labels_y_start)
            self.display.write("Temp:")
            self._wert_koordinaten['temp'] = (wert_x, labels_y_start, gross_font_h)
            self._schwelle_koordinaten['temp'] = (wert_x, labels_y_start + gross_font_h, klein_font_h)
            labels_y_start += zeilenhoehe_gesamt

            # Feuchtigkeit Label + Koordinaten speichern
            self.display.set_pos(label_x, labels_y_start)
            self.display.write("Feuchte:")
            self._wert_koordinaten['hum'] = (wert_x, labels_y_start, gross_font_h)
            self._schwelle_koordinaten['hum'] = (wert_x, labels_y_start + gross_font_h, klein_font_h)
            labels_y_start += zeilenhoehe_gesamt

            # CO2 Label + Koordinaten speichern
            self.display.set_pos(label_x, labels_y_start)
            self.display.write("CO2:")
            self._wert_koordinaten['co2'] = (wert_x, labels_y_start, gross_font_h)
            self._schwelle_koordinaten['co2'] = (wert_x, labels_y_start + gross_font_h, klein_font_h)
            labels_y_start += zeilenhoehe_gesamt

            # VOC Label + Koordinaten speichern
            self.display.set_pos(label_x, labels_y_start)
            self.display.write("VOC:")
            self._wert_koordinaten['voc'] = (wert_x, labels_y_start, gross_font_h)
            self._schwelle_koordinaten['voc'] = (wert_x, labels_y_start + gross_font_h, klein_font_h)

            aktuelle_y = labels_y_start + zeilenhoehe_gesamt # Nächste Y-Position

        except Exception as e:
            print(f"Fehler beim Zeichnen der Sensor-Labels: {e}")
            aktuelle_y += 150 # Fallback Abstand

        # --- Koordinaten für Statuszeile ---
        try:
            self.display.set_font(self.kleiner_font)
            self._status_zeilenhoehe = self.kleiner_font.height()
            status_y = max(aktuelle_y + RANDABSTAND, DISPLAY_HOEHE - self._status_zeilenhoehe - RANDABSTAND * 2)
            status_x = RANDABSTAND * 2
            self._status_koordinaten = (status_x, status_y)
        except Exception as e:
            print(f"Fehler beim Berechnen der Status-Koordinaten: {e}")

        print("Statische Elemente gezeichnet.")

    def _backlight_ausschalten_callback(self, timer):
        """ Callback für den Timer zum Ausschalten des Backlights. """
        self.pin_backlight.off()
        self.backlight_aktiv = False
        try:
            self.backlight_timer.deinit() # Timer stoppen
        except: pass # Fehler ignorieren

    def backlight_einschalten(self):
        """ Schaltet das Backlight ein und startet den Timeout-Timer. """
        # Nur neu zeichnen, wenn Backlight vorher aus war
        neu_zeichnen = not self.backlight_aktiv
        if neu_zeichnen:
             print("Schalte Backlight ein...")
             self.pin_backlight.on()
             self.backlight_aktiv = True
             # Statische Elemente neu zeichnen, damit alles sichtbar ist
             self._statische_elemente_zeichnen()

        # Timer immer neu starten (verlängert die Zeit, wenn schon an)
        try:
            self.backlight_timer.deinit()
        except: pass
        try:
            self.backlight_timer.init(mode=Timer.ONE_SHOT,
                                      period=BACKLIGHT_TIMEOUT_MS,
                                      callback=self._backlight_ausschalten_callback)
        except Exception as e:
            print(f"Fehler beim Starten des Backlight-Timers: {e}")

    def _touch_irq_handler(self, pin):
        """ Interrupt-Handler für Touch-Eingabe. """
        self.pin_touch_irq.irq(handler=None) # Entprellung
        self.backlight_einschalten()         # Backlight aktivieren
        time.sleep_ms(200)                   # Kurze Pause
        try:
            # Interrupt wieder aktivieren
            if self.pin_touch_irq:
                 self.pin_touch_irq.irq(trigger=Pin.IRQ_FALLING, handler=self._touch_irq_handler)
        except Exception as e:
            print(f"Fehler beim Reaktivieren des Touch-Interrupts: {e}")

    def setup(self):
        """ Führt die komplette Initialisierung des Displays durch. """
        self._display_initialisieren() # Initialisiert Display und zeichnet Statik
        # Touch Interrupt einrichten
        try:
            self.pin_touch_irq.irq(trigger=Pin.IRQ_FALLING, handler=self._touch_irq_handler)
            print("Touch-Interrupt konfiguriert.")
        except Exception as e:
            print(f"Fehler beim Konfigurieren des Touch-Interrupts: {e}")
        gc.collect()

    def ist_backlight_an(self):
        """ Gibt zurück, ob die Hintergrundbeleuchtung aktuell aktiv ist. """
        return self.backlight_aktiv

    # --- Haupt-Update Funktion ---
    def display_aktualisieren(self, temp, feuchte, co2, voc,
                              temp_alarm, feuchte_alarm, co2_alarm, voc_alarm,
                              temp_schwelle, feuchte_schwelle, co2_schwelle, voc_schwelle):
        """
        Aktualisiert nur die Teile des Displays, die sich geändert haben
        (Sensorwerte, Schwellwerte, Status).
        """
        # Nichts tun, wenn Backlight aus ist
        if not self.backlight_aktiv:
           # Gespeicherte Werte zurücksetzen, damit beim nächsten Einschalten alles neu gezeichnet wird
           self._letzter_temp_wert_str = None; self._letzter_temp_schwelle_str = None
           self._letzter_feuchte_wert_str = None; self._letzte_feuchte_schwelle_str = None
           self._letzter_co2_wert_str = None; self._letzte_co2_schwelle_str = None
           self._letzter_voc_wert_str = None; self._letzte_voc_schwelle_str = None
           self._letzter_status_str = None
           return

        # Sicherstellen, dass Koordinaten initialisiert sind
        if not self._wert_koordinaten or not self._status_koordinaten or not self._schwelle_koordinaten:
             print("WARNUNG: Display Koordinaten nicht initialisiert -> Neuzeichnen.")
             self._statische_elemente_zeichnen()

             if not self._wert_koordinaten or not self._status_koordinaten or not self._schwelle_koordinaten:
                  print("FEHLER: Display Koordinaten konnten nicht initialisiert werden.")
                  return

        # --- Sensorwerte und Schwellwerte aktualisieren ---
        try:
            # Temperatur
            temp_wert_str = f"{temp:.1f} C"
            temp_farbe = ROT if temp_alarm else DUNKELGRUEN
            temp_schwelle_str = f"({temp_schwelle:.1f})"
            if temp_wert_str != self._letzter_temp_wert_str or temp_farbe != self._letzte_temp_farbe:
                x, y, h = self._wert_koordinaten['temp']
                self.display.set_font(self.grosser_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ) # Alten Wert löschen
                self.display.set_color(temp_farbe, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(temp_wert_str)
                self._letzter_temp_wert_str = temp_wert_str
                self._letzte_temp_farbe = temp_farbe
            if temp_schwelle_str != self._letzter_temp_schwelle_str:
                x, y, h = self._schwelle_koordinaten['temp']
                self.display.set_font(self.kleiner_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ) # Alten Wert löschen
                self.display.set_color(DUNKELGRAU, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(temp_schwelle_str)
                self._letzter_temp_schwelle_str = temp_schwelle_str

            # Feuchtigkeit (analog)
            feuchte_wert_str = f"{feuchte:.1f} %"
            feuchte_farbe = ROT if feuchte_alarm else DUNKELGRUEN
            feuchte_schwelle_str = f"({feuchte_schwelle:.0f}%)"
            if feuchte_wert_str != self._letzter_feuchte_wert_str or feuchte_farbe != self._letzte_feuchte_farbe:
                x, y, h = self._wert_koordinaten['hum']
                self.display.set_font(self.grosser_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ)
                self.display.set_color(feuchte_farbe, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(feuchte_wert_str)
                self._letzter_feuchte_wert_str = feuchte_wert_str
                self._letzte_feuchte_farbe = feuchte_farbe
            if feuchte_schwelle_str != self._letzte_feuchte_schwelle_str:
                x, y, h = self._schwelle_koordinaten['hum']
                self.display.set_font(self.kleiner_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ)
                self.display.set_color(DUNKELGRAU, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(feuchte_schwelle_str)
                self._letzte_feuchte_schwelle_str = feuchte_schwelle_str

            # CO2 (analog)
            co2_wert_str = f"{co2} ppm"
            co2_farbe = ROT if co2_alarm else DUNKELGRUEN
            co2_schwelle_str = f"({co2_schwelle})"
            if co2_wert_str != self._letzter_co2_wert_str or co2_farbe != self._letzte_co2_farbe:
                x, y, h = self._wert_koordinaten['co2']
                self.display.set_font(self.grosser_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ)
                self.display.set_color(co2_farbe, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(co2_wert_str)
                self._letzter_co2_wert_str = co2_wert_str
                self._letzte_co2_farbe = co2_farbe
            if co2_schwelle_str != self._letzte_co2_schwelle_str:
                x, y, h = self._schwelle_koordinaten['co2']
                self.display.set_font(self.kleiner_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ)
                self.display.set_color(DUNKELGRAU, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(co2_schwelle_str)
                self._letzte_co2_schwelle_str = co2_schwelle_str

            # VOC (analog)
            voc_wert_str = f"{voc} ppb"
            voc_farbe = ROT if voc_alarm else DUNKELGRUEN
            voc_schwelle_str = f"({voc_schwelle})"
            if voc_wert_str != self._letzter_voc_wert_str or voc_farbe != self._letzte_voc_farbe:
                x, y, h = self._wert_koordinaten['voc']
                self.display.set_font(self.grosser_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ)
                self.display.set_color(voc_farbe, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(voc_wert_str)
                self._letzter_voc_wert_str = voc_wert_str
                self._letzte_voc_farbe = voc_farbe
            if voc_schwelle_str != self._letzte_voc_schwelle_str:
                x, y, h = self._schwelle_koordinaten['voc']
                self.display.set_font(self.kleiner_font)
                self.display.fill_rectangle(x, y, WERTEBEREICH_BREITE, h, SCHWARZ)
                self.display.set_color(DUNKELGRAU, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(voc_schwelle_str)
                self._letzte_voc_schwelle_str = voc_schwelle_str

        except KeyError as e:
             # Falls Koordinaten fehlen
             print(f"FEHLER beim Zugriff auf Koordinaten (KeyError: {e}), zeichne neu.")
             self._statische_elemente_zeichnen()
        except Exception as e:
            print(f"FEHLER beim Aktualisieren der Sensor/Schwellwerte: {e}")

        # --- Statuszeile aktualisieren ---
        try:
            # Status ermitteln (verwende die übersetzten Funktionsnamen)
            wifi_text = "WLAN: OK" if wifi_setup.wlan_ist_verbunden() else "WLAN: FAIL"
            mqtt_text = "MQTT: OK" if mqtt_steuerung.mqtt_ist_verbunden() else "MQTT: FAIL"
            status_text_gesamt = f"{wifi_text}   {mqtt_text}"

            # Nur neu zeichnen, wenn sich der Text geändert hat
            if status_text_gesamt != self._letzter_status_str:
                self.display.set_font(self.kleiner_font)
                x, y = self._status_koordinaten
                hoehe = self._status_zeilenhoehe
                # Alten Status löschen (ganze Breite)
                self.display.fill_rectangle(x, y, STATUSBEREICH_BREITE, hoehe, SCHWARZ)
                # Neuen Status schreiben
                self.display.set_color(GRAU, SCHWARZ)
                self.display.set_pos(x, y)
                self.display.write(status_text_gesamt)
                self._letzter_status_str = status_text_gesamt

        except Exception as e:
            print(f"FEHLER beim Aktualisieren der Statuszeile: {e}")

    def cleanup(self):
        """ Gibt die verwendeten Ressourcen frei (Timer, Interrupts, SPI, Backlight). """
        print("Räume Display-Ressourcen auf...")
        try: self.backlight_timer.deinit()
        except: pass # Fehler ignorieren
        try: self.pin_touch_irq.irq(handler=None)
        except: pass
        try: self.spi.deinit()
        except: pass
        try: self.pin_backlight.off()
        except: pass
        print("Display Aufräumen abgeschlossen.")
        gc.collect()
