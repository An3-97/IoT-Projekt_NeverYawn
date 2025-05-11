# IoT-Projekt_NeverYawn

Das Projekt "Never-Yawn" ist ein intelligentes IoT-System zur Überwachung der Raumluftqualität. 
Es misst kontinuierlich Temperatur, Luftfeuchtigkeit, CO₂-Konzentration und den Gehalt an flüchtigen organischen Verbindungen (VOC). 
Die Messwerte werden lokal auf einem TFT-Display angezeigt und über das MQTT-Protokoll an einen Server gesendet. 
Eine Weboberfläche (Node-RED Dashboard) visualisiert die Daten in Echtzeit sowie als zeitliche Verläufe und ermöglicht die manuelle Steuerung von Aktoren und Schwellwerten. 
Die Messdaten werden zur späteren Analyse in einer MariaDB-Datenbank gespeichert.