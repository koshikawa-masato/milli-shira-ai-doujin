#!/bin/bash
# RunPodBar.app を作って起動する。使い方: ./build.sh [--install]（--install で /Applications にコピー）
set -e
cd "$(dirname "$0")"
swift build -c release 2>&1 | tail -2
APP=build/RunPodBar.app
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS"
cp .build/release/RunPodBar "$APP/Contents/MacOS/RunPodBar"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>jp.kuropanda.runpodbar</string>
  <key>CFBundleName</key><string>RunPodBar</string>
  <key>CFBundleExecutable</key><string>RunPodBar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsArbitraryLoads</key><false/></dict>
</dict></plist>
PLIST
codesign --force --sign - "$APP" 2>/dev/null || true
echo "built: $APP"
if [ "$1" = "--install" ]; then rm -rf /Applications/RunPodBar.app; cp -R "$APP" /Applications/; echo "installed: /Applications/RunPodBar.app"; fi
