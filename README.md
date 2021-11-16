# shout_and_shoot
Raspberry Pi basierende Abrufanlage (sprachgesteuert auf Begriff "Computer") für Wurfscheibenmaschinen / Tontaubenschießen.
(getestet mit Raspberry Pi 3 Model B)

## Installationsanleitung.
1. Fernbedienung der Tontauben-Wurfanlage anpassen:  
NPN-Transistor mit Basiswiderstand 1kOhm anstelle des eigentlichen Tasters verlöten.  
Basiswiderstand mit Pin 26 des Raspberry Pi verbinden.
2. Drei LEDs mit Vorwiderstand an den Pins 5, 6, 13 anschließen.  
Pin 5: LED, welche signalisiert, dass eine Tontaube abgeschossen wird  
Pin 6: LED, welche signalisiert, dass ein Mikrofon erkannt wurde  
Pin 13: LED, welche signalisiert, dass das Programm läuft
3. Zwei Taster an den Pins 17 und 27 anschließen.  
Pin 17: Taster, welcher ein Herunterfahren des Raspberry Pi veranlassen wird  
Pin 27: Taster, über welchen die Tontaube manuell abgeschossen werden kann
4. Raspberry Pi mit Raspberry Pi OS aufsetzen (ggf. noch SSH freigeben)
5. Repository clonen  
`git clone https://github.com/startbit96/shout_and_shoot.git`
6. pvrecorder und pvporcupine über pip installieren (für Hotword-Detection)  
`pip install pvrecorder`  
`pip install pvporcupine`
7. Soll das Python-Skript bei Start des Raspberry Pis automatisch ausgeführt werden, dann dies in /etc/rc.local oder als crontab einrichten.