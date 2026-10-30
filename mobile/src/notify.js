// Phone notifications (local notifications: shown by the app itself, so they also work inside Expo Go).
import { Platform } from 'react-native';

let N = null;
try {
  N = require('expo-notifications');
} catch (e) {
  N = null;
}

export async function initNotifications() {
  if (!N) return;
  try {
    N.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
      }),
    });
    if (Platform.OS === 'android') {
      await N.setNotificationChannelAsync('default', {
        name: 'Air quality alerts',
        importance: N.AndroidImportance ? N.AndroidImportance.MAX : 5,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#0f6e78',
      });
    }
  } catch (e) {
    // notifications are optional; the in-app alert always works
  }
}

export async function askPermission() {
  if (!N) return false;
  try {
    const cur = await N.getPermissionsAsync();
    if (cur && cur.granted) return true;
    const r = await N.requestPermissionsAsync();
    return !!(r && r.granted);
  } catch (e) {
    return false;
  }
}

export async function notify(title, body) {
  if (!N) return false;
  try {
    const ok = await askPermission();
    if (!ok) return false;
    await N.scheduleNotificationAsync({ content: { title, body, sound: true }, trigger: null });
    return true;
  } catch (e) {
    return false;
  }
}
