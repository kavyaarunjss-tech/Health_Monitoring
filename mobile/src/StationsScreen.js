// All 8 stations as a simple list, highest AQI first; tap one to follow it.
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, catStyle, stationShort, CAT_ORDER } from './theme';
import { Loading, Banner } from './ui';

export default function StationsScreen({ data, error, current, onPick, mode }) {
  if (error) return <Banner kind="danger">{error}</Banner>;
  if (!data) return <Loading text="Loading stations..." />;
  const rows = data.stations.slice().sort((a, b) => (b.aqi == null ? -1 : b.aqi) - (a.aqi == null ? -1 : a.aqi));
  return (
    <View>
      <Text style={st.h1}>Stations</Text>
      <Text style={st.sub}>{mode === 'live' ? 'Newest data at each station · tap one to follow it' : 'At the replay time · tap one to follow it'}</Text>
      {rows.map((x) => {
        const has = x.aqi != null;
        const stale = x.status === 'stale';
        const mine = current === x.id;
        return (
          <TouchableOpacity
            key={x.id}
            testID={'st_' + x.id}
            accessibilityRole="button"
            activeOpacity={0.8}
            onPress={() => onPick(x.id)}
            style={[st.row, mine ? st.mine : null]}
          >
            <View style={[st.dot, { backgroundColor: has && !stale ? catStyle(x.category).bg : '#4a5668' }]} />
            <View style={{ flex: 1 }}>
              <Text style={st.name}>{stationShort(x.id) + (mine ? ' · yours' : '')}</Text>
              <Text style={st.cat}>{!has ? 'No data right now' : stale ? x.category + ' · data ' + Math.round(x.age_hours) + ' h old' : x.category}</Text>
            </View>
            <Text style={[st.aqi, !has || stale ? { color: C.faint } : null]}>{has ? x.aqi : '–'}</Text>
          </TouchableOpacity>
        );
      })}
      <View style={st.legend}>
        {CAT_ORDER.map((c) => (
          <View key={c} style={{ flexDirection: 'row', alignItems: 'center', marginRight: 12, marginBottom: 6 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: catStyle(c).bg, marginRight: 6 }} />
            <Text style={{ color: C.muted, fontSize: 12 }}>{c}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  h1: { color: C.text, fontSize: 30, fontWeight: '800', letterSpacing: -0.5, marginTop: 6 },
  sub: { color: C.muted, fontSize: 15, marginTop: 4, marginBottom: 16 },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: 16, paddingHorizontal: 16, height: 64, marginBottom: 8, borderWidth: 1, borderColor: 'transparent' },
  mine: { backgroundColor: C.selBg, borderColor: '#2d4a6e' },
  dot: { width: 12, height: 12, borderRadius: 6, marginRight: 14 },
  name: { color: C.text, fontSize: 16, fontWeight: '600' },
  cat: { color: C.muted, fontSize: 13, marginTop: 2 },
  aqi: { color: C.text, fontSize: 22, fontWeight: '800' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 10 },
});
