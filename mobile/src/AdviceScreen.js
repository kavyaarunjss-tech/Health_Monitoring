// What to do: big, simple action cards first; the full sourced advice and references behind "Why?".
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Linking, StyleSheet } from 'react-native';
import { C, F, R, catStyle } from './theme';
import { Card, Muted, ActionCard, Rich, Icon, CatPill, Overline, s as ui } from './ui';

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
      <Text style={[st.h1, { marginBottom: 0 }]}>What to do</Text>
      <Text style={[st.h1, { color: C.muted, marginTop: 0 }]}>for you today</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', marginBottom: 20 }}>
        <CatPill category={p.category} label={p.category + ' · AQI ' + p.aqi} small />
        <Text style={st.for}>{groupsLabel + ' · alerts from ' + alertFrom}</Text>
      </View>

      {(p.top3 || []).map((a, i) => (
        <ActionCard key={i} index={i} icon={a.icon} marked={a.marked} text={a.text} source={a.source} />
      ))}

      <TouchableOpacity onPress={() => setOpen(!open)} accessibilityRole="button" style={st.why} testID="whyBtn">
        <Text style={{ color: C.text, fontWeight: '600', fontSize: 15, marginRight: 6 }}>{open ? 'Hide details' : 'Why? Read the details and sources'}</Text>
        <Icon name={open ? 'chevronDown' : 'chevronRight'} size={16} color={C.text} />
      </TouchableOpacity>

      {open ? (
        <View>
          <Card>
            {(p.full || []).map((a, i) => (
              <View key={i} style={{ paddingVertical: 12, borderTopWidth: i ? 1 : 0, borderTopColor: C.line }}>
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
                <Text style={{ color: C.accent, marginTop: 12, fontWeight: '600' }}>Open the CPCB AQI report [1]</Text>
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
  h1: { fontFamily: F.display, color: C.text, fontSize: 32, fontWeight: '400', letterSpacing: -1, lineHeight: 38, marginTop: 6, marginBottom: 14 },
  for: { color: C.muted, fontSize: 14, marginLeft: 10, marginTop: 2 },
  why: { height: 52, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginVertical: 6, borderRadius: R.pill, backgroundColor: C.card2 },
  kind: { color: C.accent, fontSize: 11, fontWeight: '700', letterSpacing: 1.2, marginBottom: 4 },
  foot: { color: C.faint, fontSize: 12, textAlign: 'center', lineHeight: 18, marginTop: 8, marginBottom: 12 },
});
