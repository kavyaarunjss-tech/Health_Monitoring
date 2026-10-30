#!/bin/sh
# Rebuilds app/src/main/assets/www/app.js from the Expo app source in ../mobile (needs Node + esbuild, react, react-dom).
# Usage (from android/ui-build): npm install esbuild react@19 react-dom@19 && sh build.sh
cd "$(dirname "$0")"
OUT=../app/src/main/assets/www
cp shell.js $OUT/shell.js
npx esbuild entry.js --bundle --minify --target=chrome80 --outfile=$OUT/app.js --loader:.js=jsx --jsx=transform \
  --alias:react-native=./shims/react-native.js --alias:expo-constants=./shims/expo-constants.js \
  --alias:expo-notifications=./shims/expo-notifications.js --alias:@react-native-async-storage/async-storage=./shims/async-storage.js \
  --alias:react-native-safe-area-context=./shims/safe-area.js --alias:expo-status-bar=./shims/expo-status-bar.js \
  --alias:react-native-svg=./shims/svg.js --define:process.env.NODE_ENV='"production"'
