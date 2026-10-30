// All 8 stations at a glance; tap one to make it your station.
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, catStyle, stationShort, fmtTime } from './theme';
import { Card, Muted, Loading, Banner } from './ui';

export default function StationsScreen({ data, error, current, onPick, mode }) {
  if (error) return <Banner kind="danger">{error}</Banner>;
  if (!data) return <Loading text="Loading stations..." />;
  return (
    <View>
      <Muted style={{ marginBottom: 10 }}>
        {mode === 'live'
          ? 'Newest measured AQI at each station. Tap a station to follow it.'
          : 'AQI at each station at the replay time (' + fmtTime(data.clock_end) + '). Tap a station to follow it.'}
      </Muted>
      <View style={st.grid}>
        {data.stations.map((x) => {
          const c = catStyle(x.category);
          const has = x.aqi != null;
          const stale = x.status === 'stale';
          return (
            <TouchableOpacity
              key={x.id}
              testID={'st_' + x.id}
              accessibilityRole="button"
              activeOpacity={0.8}
              onPress={() => onPick(x.id)}
              style={[st.tile, { backgroundColor: has && !stale ? c.bg : '#c9d1da' }, current === x.id ? st.current : null]}
            >
              <Text style={[st.name, { color: has && !stale ? c.fg : C.text }]} numberOfLines={1}>{stationShort(x.id)}</Text>
              <Text style={[st.aqi, { color: has && !stale ? c.fg : C.text }]}>{has ? x.aqi : '–'}</Text>
              <Text style={[st.cat, { color: has && !stale ? c.fg : C.text }]} numberOfLines={1}>
                {has ? x.category : 'No data'}
              </Text>
              {stale ? <Text style={st.stale}>{'DATA OLD · ' + Math.round(x.age_hours) + ' h'}</Text> : null}
              {current === x.id ? <Text style={[st.you, { color: has && !stale ? c.fg : C.text }]}>{'★ your station'}</Text> : null}
            </TouchableOpacity>
          );
        })}
      </View>
      <Card>
        <Text style={{ fontWeight: '700', color: C.text, marginBottom: 6 }}>CPCB AQI categories</Text>
        {[
          ['Good', '0–50'],
          ['Satisfactory', '51–100'],
          ['Moderate', '101–200'],
          ['Poor', '201–300'],
          ['Very Poor', '301–400'],
          ['Severe', '401–500'],
        ].map(([n, r]) => (
          <View key={n} style={{ flexDirection: 'row', alignItems: 'center', marginVertical: 3 }}>
            <View style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: catStyle(n).bg, marginRight: 10 }} />
            <Text style={{ color: C.text, width: 110 }}>{n}</Text>
            <Text style={{ color: C.muted }}>{r}</Text>
          </View>
        ))}
      </Card>
    </View>
  );
}

const st = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  tile: { width: '48.5%', borderRadius: 14, padding: 14, marginBottom: 10, minHeight: 118 },
  current: { borderWidth: 3, borderColor: C.navy },
  name: { fontWeight: '700', fontSize: 15 },
  aqi: { fontSize: 34, fontWeight: '800', marginTop: 4 },
  cat: { fontSize: 13, fontWeight: '600' },
  stale: { marginTop: 4, fontSize: 11, fontWeight: '800', color: C.danger },
  you: { marginTop: 4, fontSize: 11, fontWeight: '700' },
});
