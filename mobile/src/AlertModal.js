// Full-screen alert: one clear message, two actions, Continue / Dismiss.
import React from 'react';
import { Modal, View, Text, ScrollView, TouchableOpacity, StyleSheet } from 'react-native';
import { C, F, R, SH_SM, catStyle, fmtClock, pname, pastel } from './theme';
import { Btn, Icon, Orb, titleFor } from './ui';

export default function AlertModal({ alert, onContinue, onDismiss, onListen, replay, insets }) {
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
      <View style={[st.root, { paddingTop: top + 12, paddingBottom: bottom + 14 }]} testID="alertModal">
        <View style={st.orb} pointerEvents="none">
          <Orb color={c.bg} size={420} />
        </View>
        <View style={st.kickerRow}>
          <View style={[st.kickerDot, { backgroundColor: c.bg }]} />
          <Text style={st.kicker}>{(alert.escalation ? 'Update · ' : '') + 'Air quality alert' + (replay ? ' · replay' : '')}</Text>
        </View>
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ flexGrow: 1, justifyContent: 'flex-end', paddingTop: 120, paddingBottom: 12 }}>
          <Text style={st.title}>{title}</Text>
          <Text style={st.body}>{body}</Text>
          <View style={st.meta}>
            <View style={[st.metaPill, { backgroundColor: c.bg }]}>
              <Text style={{ color: c.fg, fontWeight: '700', fontSize: 13 }}>{cat}</Text>
            </View>
            <Text style={st.metaText}>{'+' + f.horizon + ' h forecast' + (f.dominant ? '  ·  mainly ' + pname(f.dominant) : '')}</Text>
          </View>
          {acts.map((a, i) => {
            const t = pastel(i);
            return (
              <View key={i} style={st.act}>
                <View style={[st.actIcon, { backgroundColor: t.bg }]}>
                  <Icon name={a.icon || 'info'} size={20} color={t.fg} />
                </View>
                <View style={{ flex: 1, marginLeft: 14 }}>
                  <Text style={st.actTitle}>{titleFor(a.icon)}</Text>
                  <Text style={st.actText} numberOfLines={3}>{a.text + (a.source ? ' ' + a.source : '')}</Text>
                </View>
              </View>
            );
          })}
        </ScrollView>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Btn testID="continueBtn" title={replay ? 'Continue replay' : 'Got it'} onPress={onContinue} style={{ flex: 1 }} />
          {onListen ? (
            <TouchableOpacity testID="alertListen" accessibilityRole="button" accessibilityLabel="Listen to this alert" onPress={() => onListen(alert)} style={st.listen}>
              <Icon name="speaker" size={22} color={C.text} />
            </TouchableOpacity>
          ) : null}
        </View>
        <Btn title="Dismiss" kind="ghost" small onPress={onDismiss} style={{ marginTop: 4 }} />
        <Text style={st.note}>Not medical advice · Emergency: 112</Text>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg, paddingHorizontal: 22, overflow: 'hidden' },
  orb: { position: 'absolute', right: -150, top: -150 },
  kickerRow: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', backgroundColor: C.card, borderRadius: R.pill, paddingHorizontal: 12, height: 32, ...SH_SM },
  kickerDot: { width: 8, height: 8, borderRadius: 4, marginRight: 8 },
  kicker: { color: C.text, fontSize: 13, fontWeight: '600' },
  title: { fontFamily: F.display, color: C.text, fontSize: 34, fontWeight: '400', lineHeight: 40, letterSpacing: -1.1 },
  body: { color: C.soft, fontSize: 16, lineHeight: 24, marginTop: 12 },
  meta: { flexDirection: 'row', alignItems: 'center', marginTop: 16, marginBottom: 20, flexWrap: 'wrap' },
  metaPill: { borderRadius: R.pill, paddingHorizontal: 12, paddingVertical: 5, marginRight: 10 },
  metaText: { color: C.muted, fontSize: 13 },
  act: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: R.xl, padding: 14, marginBottom: 10, ...SH_SM },
  actIcon: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center' },
  actTitle: { color: C.text, fontSize: 15, fontWeight: '600' },
  actText: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 2 },
  listen: { width: 54, height: 54, borderRadius: 27, marginLeft: 10, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', ...SH_SM },
  note: { color: C.faint, fontSize: 12, textAlign: 'center', marginTop: 2 },
});
