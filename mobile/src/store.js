// Saves the profile and settings on the phone (no account needed).
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'aqhealth.v1';

export async function loadAll() {
  try {
    const s = await AsyncStorage.getItem(KEY);
    return s ? JSON.parse(s) : null;
  } catch (e) {
    return null;
  }
}

export async function saveAll(data) {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(data));
  } catch (e) {
    // storage full or unavailable: the app still works for this session
  }
}
