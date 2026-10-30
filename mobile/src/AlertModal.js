// Full-screen alert: one clear message, two actions, Continue / Dismiss.
import React from 'react';
import { Modal, View, Text, ScrollView, StyleSheet } from 'react-native';
import { C, catStyle, fmtClock, pname } from './theme';
import { Btn, Icon, titleFor } from './ui';

export default function AlertModal({ alert, onContinue, onDismiss, replay, insets }) {
  if (!alert) return null;
  const f = alert.f;
  const likely = alert.level === 'likely';
  const cat = likely ? f.category : f.category_high;
  const c = catStyle(cat);
  const when = fmtClock(f.target_end, alert.issued);
  const title = likely ? cat + ' air coming at ' + when : cat + ' air possible at ' + when;
  const body = likely
    ? 'At ' + alert.stationName + ' the AQI will be around ' + f.aqi + ' (likely ' + f.range_low + '–' + f.range_high + '). That is above your limit of ' + alert.alertFrom + '.'
    : 'At ' + alert.stationName + ' the AQI could reach ' + f.range_high + ' (forecast ' + f.aqi + '). Your limit is ' + alert.alertFrom + '.';
  const acts = (alert.actions || []).slice(0, 2);
  const top = (insets && insets.top) || 24;
  const bottom = (insets && insets.bottom) || 16;
  return (
    <Modal visible animationType="fade" onRequestClose={onDismiss} statusBarTranslucent>
      <View style={[st.root, { paddingTop: top + 16, paddingBottom: bottom + 16 }]} testID="alertModal">
        <Text style={st.kicker}>{(alert.escalation ? 'UPDATE · ' : '') + 'AIR QUALITY ALERT' + (replay ? ' · REPLAY' : '')}</Text>
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', paddingVertical: 16 }}>
          <View style={[st.iconBox, { backgroundColor: C.warnBg }]}>
            <Icon name="alert" size={42} color={C.warnIcon} />
          </View>
          <Text style={st.title}>{title}</Text>
          <Text style={st.body}>{body}</Text>
          <View style={st.meta}>
            <View style={[st.dot, { backgroundColor: c.bg }]} />
            <Text style={st.metaText}>{'+' + f.horizon + ' h forecast' + (f.dominant ? ' · mainly ' + pname(f.dominant) : '')}</Text>
          </View>
          {acts.map((a, i) => (
            <View key={i} style={st.act}>
              <Icon name={a.icon || 'info'} size={24} />
              <View style={{ flex: 1, marginLeft: 14 }}>
                <Text style={st.actTitle}>{titleFor(a.icon)}</Text>
                <Text style={st.actText} numberOfLines={3}>{a.text + (a.source ? ' ' + a.source : '')}</Text>
              </View>
            </View>
          ))}
        </ScrollView>
        <Text style={st.note}>Not medical advice · Emergency: 112</Text>
        <Btn testID="continueBtn" title={replay ? 'Continue replay' : 'Got it'} onPress={onContinue} />
        <Btn title="Dismiss" kind="ghost" small onPress={onDismiss} style={{ marginTop: 6 }} />
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg, paddingHorizontal: 24 },
  kicker: { color: C.warnIcon, fontSize: 12, fontWeight: '800', letterSpacing: 1.2 },
  iconBox: { width: 84, height: 84, borderRadius: 26, alignItems: 'center', justifyContent: 'center', marginBottom: 24 },
  title: { color: C.text, fontSize: 32, fontWeight: '800', lineHeight: 38, letterSpacing: -0.5 },
  body: { color: C.soft, fontSize: 17, lineHeight: 25, marginTop: 10 },
  meta: { flexDirection: 'row', alignItems: 'center', marginTop: 12, marginBottom: 20 },
  dot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  metaText: { color: C.muted, fontSize: 13 },
  act: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: 16, padding: 16, marginBottom: 10 },
  actTitle: { color: C.text, fontSize: 16, fontWeight: '700' },
  actText: { color: C.muted, fontSize: 13, lineHeight: 18, marginTop: 2 },
  note: { color: C.faint, fontSize: 13, textAlign: 'center', marginBottom: 12 },
});
