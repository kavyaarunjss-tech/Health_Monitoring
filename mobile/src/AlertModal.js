// The alert pop-up: forecast, likely range and short personal advice, with Continue / Dismiss.
import React from 'react';
import { Modal, View, Text, ScrollView, StyleSheet } from 'react-native';
import { C, catStyle, fmtTime, pname } from './theme';
import { Btn, Rich, Pill } from './ui';

export default function AlertModal({ alert, onContinue, onDismiss, replay }) {
  if (!alert) return null;
  const f = alert.f;
  const c = catStyle(alert.level === 'likely' ? f.category : f.category_high);
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onDismiss}>
      <View style={st.backdrop}>
        <View style={[st.sheet, { borderTopColor: c.bg }]} testID="alertModal">
          <Text style={st.kicker}>{alert.escalation ? 'UPDATE · ' + alert.escalation.toUpperCase() : replay ? 'REPLAY DEMO ALERT' : 'AIR QUALITY ALERT'}</Text>
          <Text style={st.title}>{alert.title}</Text>
          <Text style={st.station}>{alert.stationName}</Text>
          <View style={st.fcRow}>
            <Text style={st.aqi}>{f.aqi}</Text>
            <View style={{ marginLeft: 12, flex: 1 }}>
              <Pill category={f.category} />
              <Text style={st.meta}>{'for ' + fmtTime(f.target_end) + ' (+' + f.horizon + ' h)'}</Text>
              <Text style={st.meta}>
                {'likely ' + f.range_low + '–' + f.range_high + (f.dominant ? ' · mainly ' + pname(f.dominant) : '')}
              </Text>
            </View>
          </View>
          <Text style={st.issued}>{'Issued ' + fmtTime(alert.issued) + '. Your alert level: AQI ' + alert.alertFrom + '.'}</Text>
          <ScrollView style={{ maxHeight: 260 }}>
            {(alert.lines || []).map((l, i) => (
              <View key={i} style={st.line}>
                <Text style={st.bullet}>{'•'}</Text>
                <View style={{ flex: 1 }}>
                  <Rich text={l.marked || l.text} style={st.lineText} />
                  {l.source ? <Text style={st.src}>{l.source}</Text> : null}
                </View>
              </View>
            ))}
            <Text style={st.note}>Not medical advice. In an emergency call 112.</Text>
          </ScrollView>
          <View style={st.btns}>
            <Btn title="Dismiss" kind="secondary" onPress={onDismiss} style={{ flex: 1, marginRight: 8 }} />
            <Btn testID="continueBtn" title={replay ? 'Continue replay' : 'OK'} onPress={onContinue} style={{ flex: 1.4 }} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(8,20,32,0.55)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, borderTopWidth: 8, padding: 20, paddingBottom: 28 },
  kicker: { fontSize: 12, fontWeight: '800', letterSpacing: 1, color: C.danger },
  title: { fontSize: 20, fontWeight: '800', color: C.text, marginTop: 4 },
  station: { fontSize: 14, color: C.muted, marginTop: 2 },
  fcRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  aqi: { fontSize: 48, fontWeight: '800', color: C.text },
  meta: { fontSize: 13, color: C.text, marginTop: 4 },
  issued: { fontSize: 12, color: C.muted, marginVertical: 10 },
  line: { flexDirection: 'row', marginBottom: 8 },
  bullet: { width: 16, fontSize: 16, color: C.teal },
  lineText: { fontSize: 15, lineHeight: 21, color: C.text },
  src: { fontSize: 12, color: C.muted },
  note: { fontSize: 12, color: C.muted, marginTop: 4 },
  btns: { flexDirection: 'row', marginTop: 14 },
});
