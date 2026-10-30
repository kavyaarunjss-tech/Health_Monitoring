// Entry for the Android WebView build: renders the same app code as the Expo app (../../mobile/App.js).
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from '../../mobile/App.js';
createRoot(document.getElementById('root')).render(<App />);
