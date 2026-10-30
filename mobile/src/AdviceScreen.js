// What to do: big, simple action cards first; the full sourced advice and references behind "Why?".
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Linking, StyleSheet } from 'react-native';
import { C, catStyle } from './theme';
import { Card, Muted, ActionCard, Rich, s as ui } from './ui';

const KIND_TITLE = {
  headline: 'What this level means',
  what_to_do: 'What to do',
  group: 'For your health group',
  trend: 'Next 24 hours',
  best_time: 'Best time to go out',
  pollutant: 'Main pollutant',
  tip: 'Tip',
  doctor: 'When to see a doctor',
  caution: 'Caution',
};

export default function AdviceScreen({ vm, meta, alertFrom, groupsLabel }) {
  const [open, setOpen] = useState(false);
  const p = vm && vm.personal;
  if (!p) {
    return (
      <Card>
        <Muted>No advice yet: there is no AQI for this hour. Go to Home and pick another hour or station.</Muted>
      </Card>
    );
  }
  const c = catStyle(p.category);
  return (
    <View>
      <View style={[st.pill, { borderColor: c.bg }]}>
        <View style={[st.dot, { backgroundColor: c.bg }]} />
        <Text style={st.pillText}>{p.category + ' · AQI ' + p.aqi}</Text>
      </View>
      <Text style={st.h1}>What to do</Text>
      <Text style={st.for}>{'For you: ' + groupsLabel + ' · alerts from ' + alertFrom}</Text>

      {(p.top3 || []).map((a, i) => (
        <ActionCard key={i} icon={a.icon} marked={a.marked} text={a.text} source={a.source} />
      ))}

      <TouchableOpacity onPress={() => setOpen(!open)} accessibilityRole="button" style={st.why} testID="whyBtn">
        <Text style={{ color: C.accent, fontWeight: '700', fontSize: 15 }}>{open ? 'Hide details' : 'Why? Read the details and sources'}</Text>
      </TouchableOpacity>

      {open ? (
        <View>
          <Card>
            {(p.full || []).map((a, i) => (
              <View key={i} style={{ paddingVertical: 10, borderTopWidth: i ? 1 : 0, borderTopColor: C.card2 }}>
                <Text style={st.kind}>{(KIND_TITLE[a.kind] || '').toUpperCase()}</Text>
                <Rich text={a.marked || a.text} style={ui.body} />
                {a.source ? <Text style={ui.src}>{a.source}</Text> : null}
              </View>
            ))}
          </Card>
          {meta ? (
            <Card>
              <Text style={[ui.h2, { marginBottom: 8 }]}>Sources and disclaimer</Text>
              <Text style={[ui.body, { fontSize: 13, lineHeight: 19 }]}>{meta.disclaimer}</Text>
              {Object.entries(meta.references || {}).map(([k, v]) => (
                <Text key={k} style={[ui.src, { marginTop: 8, fontSize: 13 }]}>{'[' + k + '] ' + v}</Text>
              ))}
              <TouchableOpacity onPress={() => Linking.openURL('https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf')}>
                <Text style={{ color: C.accent, marginTop: 10, fontWeight: '600' }}>Open the CPCB AQI report [1]</Text>
              </TouchableOpacity>
            </Card>
          ) : null}
        </View>
      ) : null}

      <Text style={st.foot}>Based on CPCB, Health Ministry (NCDC) and WHO guidance.{'\n'}Not medical advice · Emergency: 112</Text>
    </View>
  );
}

const st = StyleSheet.create({
  pill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, marginTop: 6 },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  pillText: { color: C.text, fontSize: 12, fontWeight: '700' },
  h1: { color: C.text, fontSize: 30, fontWeight: '800', letterSpacing: -0.5, marginTop: 10 },
  for: { color: C.muted, fontSize: 15, marginTop: 4, marginBottom: 16 },
  why: { height: 48, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  kind: { color: C.accent, fontSize: 11, fontWeight: '800', letterSpacing: 0.8, marginBottom: 3 },
  foot: { color: C.faint, fontSize: 12, textAlign: 'center', lineHeight: 18, marginTop: 8, marginBottom: 12 },
});
