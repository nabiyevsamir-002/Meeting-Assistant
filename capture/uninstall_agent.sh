#!/bin/bash
# Capture agentini silir (konfiqurasiya faylı istəyə görə saxlanılır)
PLIST="$HOME/Library/LaunchAgents/com.meeting-assistant.capture.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Agent dayandırıldı və LaunchAgent silindi."
echo "Konfiqurasiyanı da silmək üçün:"
echo "  rm -rf \"$HOME/Library/Application Support/meeting-assistant\""
