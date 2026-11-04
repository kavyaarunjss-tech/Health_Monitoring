// All 8 stations as a simple list, highest AQI first; tap one to follow it.
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, F, R, SH_SM, catStyle, stationShort, stationName, CAT_ORDER } from './theme';
import { Loading, Banner, Overline, Icon } from './ui';

export default function StationsScreen({ data, error, current, onPick, mode }) {
  if (error) return <Banner kind="danger">{error}</Banner>;
  if (!data) return <Loading text="Loading stations..." />;
  const rows = data.stations.slice().sort((a, b) => (b.aqi == null ? -1 : b.aqi) - (a.aqi == null ? -1 : a.aqi));
  return (
    <View>
      <Text style={st.h1}>Stations</Text>
      <Text style={[st.h1, { color: C.muted, marginTop: 0 }]}>across Karnataka</Text>
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
            <View style={[st.badge, has && !stale ? { backgroundColor: catStyle(x.category).bg } : st.badgeEmpty]}>
              <Text style={[st.aqi, { color: has && !stale ? catStyle(x.category).fg : C.muted }]}>{has ? x.aqi : '–'}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={st.name} numberOfLines={1}>{stationShort(x.id)}</Text>
                {mine ? <View style={st.yours}><Text style={st.yoursText}>Yours</Text></View> : null}
              </View>
              <Text style={st.cat} numberOfLines={1}>{!has ? 'No data right now' : stale ? x.category + ' · data ' + Math.round(x.age_hours) + ' h old' : x.category}</Text>
            </View>
            <Icon name="chevronRight" size={18} color={C.faint} />
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
  h1: { fontFamily: F.display, color: C.text, fontSize: 32, fontWeight: '400', letterSpacing: -1, lineHeight: 38, marginTop: 6 },
  sub: { color: C.muted, fontSize: 15, marginTop: 6, marginBottom: 20 },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: R.xl, paddingHorizontal: 12, paddingRight: 14, height: 72, marginBottom: 10, borderWidth: 1.5, borderColor: 'transparent', ...SH_SM },
  mine: { borderColor: C.selBorder, backgroundColor: C.selBg },
  badge: { width: 50, height: 50, borderRadius: 25, alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  badgeEmpty: { backgroundColor: C.card2 },
  name: { color: C.text, fontSize: 16, fontWeight: '600', flexShrink: 1 },
  cat: { color: C.muted, fontSize: 13, marginTop: 3 },
  aqi: { fontSize: 18, fontWeight: '700' },
  yours: { marginLeft: 8, backgroundColor: C.primary, borderRadius: R.pill, paddingHorizontal: 8, paddingVertical: 2 },
  yoursText: { color: C.onPrimary, fontSize: 11, fontWeight: '600' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 12 },
});
