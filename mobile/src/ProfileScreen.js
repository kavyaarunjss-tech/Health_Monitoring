// Profile and settings: name, station, health groups, alert level, notifications, server address, replay period.
import React, { useState } from 'react';
import { View, Text, TextInput, Switch, StyleSheet } from 'react-native';
import { C, STATIONS, GROUPS, ALERT_CHOICES, defaultAlert, alertLevel } from './theme';
import { Card, H2, Muted, Chip, Btn, Banner } from './ui';

export default function ProfileScreen({ initial, welcome, onSave, onTestServer, onTestNotification }) {
  const [p, setP] = useState(initial);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setP((x) => ({ ...x, [k]: v }));
  const def = defaultAlert(p.groups);
  const level = alertLevel(p);

  const toggleGroup = (g) => {
    const groups = p.groups.includes(g) ? p.groups.filter((x) => x !== g) : p.groups.concat(g);
    const d = defaultAlert(groups);
    setP((x) => ({ ...x, groups, alertOverride: x.alertOverride && x.alertOverride < d ? x.alertOverride : null }));
  };

  const testServer = async () => {
    setBusy(true);
    setMsg(null);
    const r = await onTestServer(p.server);
    setMsg(r);
    setBusy(false);
  };

  return (
    <View>
      {welcome ? (
        <Card accent={C.teal}>
          <Text style={st.welcome}>Welcome to AQ Health</Text>
          <Muted>
            Air quality forecasts for 8 Karnataka stations with personal health alerts. Tell us a little about you so the advice fits you. Everything
            stays on this phone.
          </Muted>
        </Card>
      ) : null}

      <Card>
        <H2>About you</H2>
        <Text style={st.label}>Your name (optional)</Text>
        <TextInput value={p.name} onChangeText={(v) => set('name', v)} placeholder="e.g. Kavya" style={st.input} />
        <Text style={[st.label, { marginTop: 14 }]}>Your nearest station</Text>
        <View style={st.wrap}>
          {STATIONS.map((x) => (
            <Chip key={x.id} label={x.short} active={p.station === x.id} onPress={() => set('station', x.id)} />
          ))}
        </View>
        <Text style={[st.label, { marginTop: 6 }]}>Does any of this apply to you? (tap all that apply)</Text>
        <View style={st.wrap}>
          {GROUPS.map((g) => (
            <Chip key={g.id} label={g.label} active={p.groups.includes(g.id)} onPress={() => toggleGroup(g.id)} />
          ))}
        </View>
        <Muted>{p.groups.length ? 'You are in a more sensitive group, so you get advice earlier.' : 'None selected: advice for a healthy adult.'}</Muted>
      </Card>

      <Card>
        <H2>Alerts</H2>
        <Text style={st.label}>{'Alert me when the forecast AQI reaches: ' + level}</Text>
        <View style={st.wrap}>
          {ALERT_CHOICES.filter((v) => v <= def).map((v) => (
            <Chip key={v} label={v === def ? v + ' (recommended)' : String(v)} active={level === v} onPress={() => set('alertOverride', v === def ? null : v)} />
          ))}
        </View>
        <Muted>You can make alerts earlier (lower number) but not later than the recommended level for your profile.</Muted>
        <Row label="Phone notifications" value={p.notify} onChange={(v) => set('notify', v)} />
        <Row label="Pause the replay when an alert comes" value={p.pauseOnAlert} onChange={(v) => set('pauseOnAlert', v)} />
        <Btn title="Send a test notification" kind="secondary" small onPress={onTestNotification} style={{ marginTop: 10 }} />
      </Card>

      <Card>
        <H2>Data mode</H2>
        <View style={st.wrap}>
          <Chip label="Replay demo (past data)" active={p.mode === 'replay'} onPress={() => set('mode', 'replay')} />
          <Chip label="Live data" active={p.mode === 'live'} onPress={() => set('mode', 'live')} />
        </View>
        {p.mode === 'replay' ? (
          <View>
            <Text style={st.label}>Replay period</Text>
            <View style={st.wrap}>
              <Chip label="17 Apr – 29 May 2026 (more events)" active={p.period === 'validation'} onPress={() => set('period', 'validation')} />
              <Chip label="29 May – 21 Jul 2026 (monsoon)" active={p.period === 'test'} onPress={() => set('period', 'test')} />
            </View>
            <Muted>Replay plays past days hour by hour, using only data that was available at each hour, exactly like a live system.</Muted>
          </View>
        ) : (
          <Muted>Live mode needs the laptop's live database (data/aqi.db). The government data feed for these stations stopped on 13 Oct 2026.</Muted>
        )}
      </Card>

      <Card>
        <H2>Laptop server</H2>
        <Muted>The app reads data from the project's server on your laptop. Phone and laptop must be on the same Wi-Fi or hotspot.</Muted>
        <TextInput
          value={p.server}
          onChangeText={(v) => set('server', v)}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://192.168.1.5:8000"
          style={[st.input, { marginTop: 10 }]}
        />
        <Btn title={busy ? 'Checking...' : 'Test connection'} kind="secondary" small onPress={testServer} disabled={busy} style={{ marginTop: 10 }} />
        {msg ? <Banner kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Banner> : null}
      </Card>

      <Btn testID="saveProfile" title={welcome ? 'Start' : 'Save'} onPress={() => onSave(p)} style={{ marginBottom: 24 }} />
    </View>
  );
}

function Row({ label, value, onChange }) {
  return (
    <View style={st.row}>
      <Text style={{ flex: 1, color: C.text, fontSize: 15 }}>{label}</Text>
      <Switch value={!!value} onValueChange={onChange} trackColor={{ true: C.teal, false: '#c9d1da' }} thumbColor="#ffffff" />
    </View>
  );
}

const st = StyleSheet.create({
  welcome: { fontSize: 22, fontWeight: '800', color: C.navy, marginBottom: 6 },
  label: { fontWeight: '600', color: C.text, marginBottom: 8, fontSize: 14 },
  input: { borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16, color: C.text, backgroundColor: '#fff' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.border, marginTop: 10 },
});
