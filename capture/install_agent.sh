#!/bin/bash
# =====================================================================
# Capture agentinin quraşdırılması (macOS LaunchAgent) — BİR DƏFƏLİK.
#
#   bash capture/install_agent.sh
#
# Nə edir:
#   1. Konfiqurasiya faylı yaradır (API ünvanı + UI istifadəçi/şifrə)
#   2. LaunchAgent qeydiyyatı — Mac açılanda agent avtomatik qalxır
#   3. Mikrofon icazəsi üçün 1 saniyəlik test yazması edir
#
# Bundan sonra: UI-da "Başlat" basdığınız an səs avtomatik tutulur.
# Silmək üçün: bash capture/uninstall_agent.sh
# =====================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
CONFIG_DIR="$HOME/Library/Application Support/meeting-assistant"
PLIST="$HOME/Library/LaunchAgents/com.meeting-assistant.capture.plist"

# Virtual mühit yoxdursa xəbərdarlıq
if [ ! -x "$PYTHON" ]; then
  echo "XƏTA: $PYTHON tapılmadı. Əvvəlcə layihə kökündə 'make install' işə salın."
  exit 1
fi

# --- 1. Konfiqurasiya ---
mkdir -p "$CONFIG_DIR"
if [ -f "$CONFIG_DIR/config" ]; then
  echo "Mövcud konfiqurasiya saxlanılır: $CONFIG_DIR/config"
else
  read -p  "API ünvanı [https://api.visualkey.az]: " API
  read -p  "UI istifadəçi adı [samir]: " USERNAME
  read -s -p "UI şifrəsi: " PASSWORD; echo
  cat > "$CONFIG_DIR/config" <<EOF
API=${API:-https://api.visualkey.az}
USERNAME=${USERNAME:-samir}
PASSWORD=$PASSWORD
DEVICE=blackhole
POLL_SECONDS=5
CHUNK_SECONDS=20
EOF
  chmod 600 "$CONFIG_DIR/config"
  echo "Konfiqurasiya yazıldı (yalnız siz oxuya bilərsiniz)."
fi

# --- 2. LaunchAgent ---
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.meeting-assistant.capture</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$PROJECT_DIR/capture/agent.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/meeting-assistant-capture.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/meeting-assistant-capture.log</string>
</dict>
</plist>
EOF

# Köhnə instansı söndürüb yenisini yükləyirik
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "LaunchAgent yükləndi — agent artıq arxa planda işləyir."

# --- 3. Mikrofon icazəsi üçün test yazması ---
# İlk yazma macOS-un mikrofon icazəsi pəncərəsini açır; burada Terminal-dan
# işə salındığı üçün pəncərə görünür və icazə python-a verilir.
echo "Mikrofon icazəsi üçün 1 saniyəlik test yazması edilir..."
"$PYTHON" - <<'PYEOF' || echo "Qeyd: test alınmadı — BlackHole hələ görünmür ola bilər (Mac restartı lazımdır)"
import sounddevice as sd
sd.rec(16000, samplerate=16000, channels=1, dtype="int16"); sd.wait()
print("Mikrofon icazəsi OK ✅")
PYEOF

echo ""
echo "✅ Hazırdır! İzləmək üçün: tail -f ~/Library/Logs/meeting-assistant-capture.log"
