// Health advice: summary first, then all advice lines with their sources, the disclaimer and the reference list.
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Linking } from 'react-native';
import { C } from './theme';
import { Card, H2, Muted, Pill, ActionRow, Rich, Banner, s } from './ui';

const KIND_TITLE = {
  headline: 'What this level means',
  what_to_do: 'What to do',
  group: 'For you',
  trend: 'Next 24 hours',
  best_time: 'Best time to go out',
  pollutant: 'Main pollutant',
  tip: 'Tip',
  doctor: 'When to see a doctor',
  caution: 'Caution',
};

export default function AdviceScreen({ vm, meta, alertFrom }) {
  const [showRefs, setShowRefs] = useState(false);
  const p = vm && vm.personal;
  if (!p) {
    return (
      <Card>
        <Muted>No advice yet: there is no AQI for this hour. Go to Home and pick another hour or station.</Muted>
      </Card>
    );
  }
  const basis = p.basis && p.basis.label;
  return (
    <View>
      <Card accent={C.teal}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
          <Pill category={p.category} />
          <Text style={{ marginLeft: 10, fontSize: 18, fontWeight: '800', color: C.text }}>AQI {p.aqi}</Text>
        </View>
        <Muted>
          {(basis ? 'Based on ' + basis + '. ' : '') + 'Your alert level: AQI ' + alertFrom + '. ' + levelText(p.level)}
        </Muted>
      </Card>

      <Card>
        <H2>Your top 3 actions</H2>
        {(p.top3 || []).map((a, i) => (
          <ActionRow key={i} icon={a.icon} marked={a.marked} text={a.text} source={a.source} />
        ))}
      </Card>

      <Card>
        <H2>All advice for you</H2>
        {(p.full || []).map((a, i) => (
          <View key={i} style={{ paddingVertical: 8, borderTopWidth: i ? 1 : 0, borderTopColor: C.border }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.teal, marginBottom: 2 }}>{(KIND_TITLE[a.kind] || '').toUpperCase()}</Text>
            <Rich text={a.marked || a.text} style={s.body} />
            {a.source ? <Text style={s.src}>{a.source}</Text> : null}
          </View>
        ))}
      </Card>

      <Banner kind="warn">Not medical advice. In an emergency call 112.</Banner>

      {meta ? (
        <Card>
          <TouchableOpacity onPress={() => setShowRefs(!showRefs)} accessibilityRole="button">
            <H2 right={<Text style={{ color: C.teal, fontWeight: '700' }}>{showRefs ? 'Hide ▴' : 'Show ▾'}</Text>}>
              Sources and disclaimer
            </H2>
          </TouchableOpacity>
          {showRefs ? (
            <View>
              <Text style={[s.body, { fontSize: 13, lineHeight: 19 }]}>{meta.disclaimer}</Text>
              {Object.entries(meta.references || {}).map(([k, v]) => (
                <Text key={k} style={[s.muted, { marginTop: 8 }]}>{'[' + k + '] ' + v}</Text>
              ))}
              <TouchableOpacity onPress={() => Linking.openURL('https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf')}>
                <Text style={{ color: C.teal, marginTop: 10, fontWeight: '600' }}>Open the CPCB AQI report [1]</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <Muted>Every health line comes from CPCB, NCDC (Health Ministry) or WHO guidance. Numbers in brackets are the sources.</Muted>
          )}
        </Card>
      ) : null}
    </View>
  );
}

function levelText(level) {
  if (level === 'alert') return 'This is at or above your alert level.';
  if (level === 'advisory') return 'Take some care (advisory level).';
  return 'No special precautions needed for your profile.';
}
