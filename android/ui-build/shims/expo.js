// Test-only shims for the Expo modules the app uses.
import React from 'react';

export const Constants = { expoConfig: { hostUri: (typeof window !== 'undefined' && window.__HOST) || '127.0.0.1:8081' } };

window.__notifs = [];
export const Notifications = {
  setNotificationHandler() {},
  setNotificationChannelAsync: async () => {},
  AndroidImportance: { MAX: 5 },
  getPermissionsAsync: async () => ({ granted: true }),
  requestPermissionsAsync: async () => ({ granted: true }),
  scheduleNotificationAsync: async (req) => {
    window.__notifs.push(req.content);
    if (window.__aqNotify) window.__aqNotify(req.content.title, req.content.body);
  },
};

export const AsyncStorage = {
  getItem: async (k) => localStorage.getItem(k),
  setItem: async (k, v) => localStorage.setItem(k, v),
};

export function SafeAreaProvider({ children }) {
  return children;
}
export const useSafeAreaInsets = () => ({ left: 0, right: 0, ...(window.__INSETS || { top: 24, bottom: 16 }) });
export function StatusBar() {
  return null;
}
