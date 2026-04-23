# OpenCode Server Setup

## Überblick

Dieses Dokument beschreibt, wie du OpenCode als Server-Instanz startest und mit ExecQueue verbindest.

---

## 1. OpenCode-Verzeichnis finden

```bash
# Prüfen, wo opencode installiert ist
which opencode

# Oder im Home-Verzeichnis suchen
find ~ -name "opencode" -type d 2>/dev/null | head -5

# Oder direkt auflisten
ls ~/opencode/
```

---

## 2. Server starten

### Option A: Mit `tmux` (Empfohlen für Development)

**Vorteile:**
- SSH kann geschlossen werden
- Server läuft weiter
- Einfache Verwaltung
- Logs sichtbar

**Schritte:**

```bash
# 1. In OpenCode-Verzeichnis wechseln
cd ~/opencode

# 2. tmux Session starten
tmux new -s opencode

# 3. Server in Session starten
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Session trennen (Server läuft weiter!)
# Drücke: Ctrl+B, dann D
```

**Wieder verbinden:**
```bash
tmux attach -t opencode
```

**Session beenden (Server stoppen):**
```bash
# Erst verbinden
tmux attach -t opencode

# Dann beenden (Ctrl+C)
# ODER aus einem anderen Terminal:
tmux send-keys -t opencode C-c
```

---

### Option B: Mit `nohup` (Einfach, aber weniger Features)

**Vorteile:**
- Sehr einfach
- Kein extra Tool nötig

**Nachteile:**
- Keine einfache Log-Ansicht
- Weniger Kontrolle

**Schritte:**

```bash
# 1. In OpenCode-Verzeichnis wechseln
cd ~/opencode

# 2. Server im Hintergrund starten
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > opencode.log 2>&1 &

# 3. Status prüfen
ps aux | grep uvicorn

# 4. Logs ansehen
tail -f opencode.log
```

**Server stoppen:**
```bash
pkill -f "uvicorn main:app"
```

---

### Option C: Mit `systemd` (Production)

**Vorteile:**
- Automatisch beim Booten
- System-Integration
- Automatische Neustarts
- System-Logs

**Schritte:**

```bash
# 1. Service-Datei erstellen
sudo nano /etc/systemd/system/opencode.service
```

**Inhalt:**
```ini
[Unit]
Description=OpenCode Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/opencode
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Service starten:**
```bash
# 2. Service neu laden
sudo systemctl daemon-reload

# 3. Service aktivieren (automatisch beim Booten)
sudo systemctl enable opencode

# 4. Service starten
sudo systemctl start opencode

# 5. Status prüfen
sudo systemctl status opencode

# 6. Logs ansehen
sudo journalctl -u opencode -f
```

**Service stoppen:**
```bash
sudo systemctl stop opencode
```

---

### Option D: Mit `PM2` (Production - Empfohlen)

**Vorteile:**
- Einfache Verwaltung
- Automatische Neustarts
- Built-in Logging
- Process Monitoring

**Schritte:**

```bash
# 1. PM2 installieren (falls nicht vorhanden)
npm install -g pm2

# 2. In OpenCode-Verzeichnis wechseln
cd ~/opencode

# 3. Server starten
pm2 start "python -m uvicorn main:app --host 0.0.0.0 --port 8000" --name opencode

# 4. PM2 beim Booten aktivieren
pm2 startup
# Ausgabe kopieren und ausführen

# 5. Prozessliste speichern
pm2 save

# 6. Logs ansehen
pm2 logs opencode

# 7. Status prüfen
pm2 status
```

**Service stoppen:**
```bash
pm2 stop opencode
pm2 delete opencode
```

---

## 3. Server testen

```bash
# 1. Lokale Verbindung testen
curl http://localhost:8000/api/health

# 2. Externe Verbindung testen (andere Maschine)
curl http://DEINE-SERVER-IP:8000/api/health

# 3. Server-IP herausfinden
hostname -I
```

**Erwartete Antwort:**
```json
{
  "status": "healthy",
  "version": "..."
}
```

---

## 4. Firewall konfigurieren

```bash
# Port 8000 für externe Zugriffe öffnen (UFW)
sudo ufw allow 8000/tcp

# Status prüfen
sudo ufw status
```

---

## 5. ExecQueue konfigurieren

### `.env` Datei in ExecQueue aktualisieren:

```env
# OpenCode API Konfiguration
OPENCODE_BASE_URL=http://DEINE-SERVER-IP:8000

# Optional: Timeout und Retries anpassen
OPENCODE_TIMEOUT=120
OPENCODE_MAX_RETRIES=3
```

### Beispiel mit öffentlicher IP:
```env
OPENCODE_BASE_URL=http://34.123.45.67:8000
```

### Beispiel mit Domain (empfohlen):
```env
OPENCODE_BASE_URL=https://opencode.deinedomain.de
```

---

## 6. Troubleshooting

### Server startet nicht

```bash
# Logs prüfen
tail -f opencode.log

# Oder bei systemd
sudo journalctl -u opencode -f

# Oder bei PM2
pm2 logs opencode
```

### Port 8000 bereits belegt

```bash
# Prozess finden
sudo lsof -i :8000

# Prozess beenden
sudo kill -9 <PID>

# Oder anderen Port verwenden
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

### Verbindung verweigert

```bash
# Firewall prüfen
sudo ufw status

# Port prüfen
netstat -tulpn | grep 8000

# Test von extern
curl -v http://DEINE-SERVER-IP:8000/api/health
```

### Server nach SSH-Disconnect gestoppt

```bash
# Lösung: tmux, nohup, systemd oder PM2 verwenden (siehe oben)

# Aktuelle Prozesse prüfen
ps aux | grep uvicorn

# Wenn gestoppt: neu starten mit einer der Methoden oben
```

---

## 7. Quick-Start Commands

### Alles in einem Rutsch (tmux):

```bash
cd ~/opencode && \
tmux new -d -s opencode && \
tmux send-keys -t opencode "python -m uvicorn main:app --host 0.0.0.0 --port 8000" Enter && \
echo "✓ OpenCode Server gestartet!" && \
echo "✓ tmux attach: tmux attach -t opencode" && \
echo "✓ Server-IP: $(hostname -I)"
```

### Alles in einem Rutsch (nohup):

```bash
cd ~/opencode && \
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > opencode.log 2>&1 & \
echo "✓ OpenCode Server gestartet!" && \
echo "✓ Logs: tail -f opencode.log" && \
echo "✓ Server-IP: $(hostname -I)"
```

---

## 8. URL nach Neustart

| Szenario | URL ändert sich? |
|----------|------------------|
| Gleicher Server, gleicher Port | ✅ **JA, bleibt gleich** |
| Server wird neu gestartet | `http://DEINE-IP:8000` |
| Server gestoppt & neu gestartet | `http://DEINE-IP:8000` |
| **Anderer Port** | ❌ NEIN, ändert sich |
| `--port 8001` statt 8000 | `http://DEINE-IP:8001` |
| **Dynamische IP ohne feste IP** | ❌ NEIN, kann sich ändern |
| Cloud-Server ohne feste IP | IP ändert sich bei Neustart |

**Tipp:** Verwende eine Domain oder feste IP für Production!

---

## 9. Zusammenfassung

| Methode | SSH offen? | Autom. Start | Logging | Empfehlung |
|---------|------------|--------------|---------|------------|
| **tmux** | ❌ Nein | ❌ Manuel | ✅ Gut | Development |
| **nohup** | ❌ Nein | ❌ Manuel | ⚠️ Einfach | Quick Start |
| **systemd** | ❌ Nein | ✅ Ja | ✅ System | Production |
| **PM2** | ❌ Nein | ✅ Ja | ✅ Excellent | Production |

---

## 10. Nächste Schritte

1. ✅ OpenCode Server starten (eine der Methoden oben)
2. ✅ Server mit `curl` testen
3. ✅ Firewall konfigurieren (Port 8000)
4. ✅ `.env` in ExecQueue aktualisieren
5. ✅ Tests in ExecQueue ausführen

---

**Dokument erstellt:** 2026-04-23  
**Version:** 1.0
