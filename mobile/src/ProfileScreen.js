// Profile and settings: name, station, health groups, alert level, notifications, server address, replay period.
import React, { useState } from 'react';
import { View, Text, TextInput, StyleSheet } from 'react-native';
import { C, F, R, THEME, THEME_MODE, setThemeMode, themeSwitchAvailable, STATIONS, GROUPS, ALERT_CHOICES, defaultAlert, alertLevel } from './theme';
import { Card, H2, Muted, Chip, Btn, Banner, Segmented, Toggle, Orb, Overline } from './ui';
import { offlineAvailable, isOffline, OFFLINE_SERVER } from './api';
import { mailAvailable, mailStatus, saveSender, clearSender, validEmail } from './mail';

export default function ProfileScreen({ initial, welcome, onSave, onTestServer, onTestNotification, onTestMail, onSummaryMail }) {
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

  const [mail, setMail] = useState(mailStatus());
  const [sender, setSender] = useState(mailStatus().sender || '');
  const [appPass, setAppPass] = useState('');
  const [mailMsg, setMailMsg] = useState(null);
  const [mailBusy, setMailBusy] = useState(false);
  const canMail = mail.configured && validEmail(p.email);

  const saveMailSender = () => {
    const err = saveSender(sender.trim() || p.email.trim(), appPass);
    if (err) {
      setMailMsg({ ok: false, text: err });
      return;
    }
    setAppPass('');
    setMail(mailStatus());
    setMailMsg({ ok: true, text: 'Sending account saved on this phone. Now tap "Send test e-mail".' });
  };
  const removeMailSender = () => {
    clearSender();
    setMail(mailStatus());
    setMailMsg({ ok: true, text: 'Sending account removed from this phone.' });
  };
  const runMail = async (fn) => {
    if (!validEmail(p.email)) {
      setMailMsg({ ok: false, text: 'Enter your e-mail address first.' });
      return;
    }
    setMailBusy(true);
    setMailMsg({ ok: true, text: 'Sending...' });
    const r = await fn(p);
    setMailMsg(r);
    setMailBusy(false);
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
        <View style={st.welcomeBox}>
          <View style={st.welcomeOrb} pointerEvents="none">
            <Orb color={C.accent} size={190} />
          </View>
          <Overline>Air quality · Karnataka</Overline>
          <Text style={st.welcome}>Know the air{'\n'}before you{'\n'}step out.</Text>
          <Muted style={{ maxWidth: 320 }}>
            Air quality forecasts for 8 Karnataka stations with personal health alerts. Tell us a little about you so the advice fits you. Everything
            stays on this phone.
          </Muted>
        </View>
      ) : null}

      <Card>
        <H2>About you</H2>
        <Text style={st.label}>Your name (optional)</Text>
        <TextInput value={p.name} onChangeText={(v) => set('name', v)} placeholder="e.g. Kavya" placeholderTextColor={C.faint} style={st.input} />
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
        <H2>E-mail alerts</H2>
        <Text style={st.label}>Your e-mail (alerts and health summaries are sent here)</Text>
        <TextInput
          value={p.email}
          onChangeText={(v) => set('email', v)}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          placeholder="you@gmail.com"
          placeholderTextColor={C.faint}
          style={st.input}
        />
        {p.email && !validEmail(p.email) ? <Text style={st.err}>This does not look like an e-mail address.</Text> : null}
        {!mailAvailable() ? (
          <Muted>E-mail is sent by the phone itself, so it works in the Android Studio app (not in Expo Go).</Muted>
        ) : (
          <View>
            <Row label="E-mail me air quality alerts" value={p.emailAlerts} onChange={(v) => set('emailAlerts', v)} />
            <Muted>Sent with the phone alert: forecast, your personal advice and the sources. At most one per minute; the same alert is never sent twice.</Muted>

            <Text style={[st.label, { marginTop: 16 }]}>Sending Gmail account</Text>
            {mail.configured ? (
              <View>
                <Text style={st.ok}>{'Ready: e-mails are sent from ' + mail.sender}</Text>
                <Btn title="Remove sending account" kind="ghost" small onPress={removeMailSender} style={{ marginTop: 4, alignSelf: 'flex-start' }} />
              </View>
            ) : (
              <View>
                <Muted>
                  Alerts are sent from a Gmail account (it can be your own). Gmail needs an App password: turn on 2-Step Verification, then open
                  myaccount.google.com/apppasswords, create one named "AQ Health" and paste the 16 letters here. Your normal password will not work.
                </Muted>
                <TextInput
                  value={sender}
                  onChangeText={setSender}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="email-address"
                  placeholder={p.email || 'sender@gmail.com'}
                  placeholderTextColor={C.faint}
                  style={[st.input, { marginTop: 10 }]}
                />
                <TextInput
                  value={appPass}
                  onChangeText={setAppPass}
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                  placeholder="App password (16 letters)"
                  placeholderTextColor={C.faint}
                  style={[st.input, { marginTop: 10 }]}
                />
                <Btn title="Save sending account" kind="secondary" small onPress={saveMailSender} style={{ marginTop: 10 }} />
                <Muted>Stored only in this app's private storage on the phone; never shown again and never sent anywhere except Gmail.</Muted>
              </View>
            )}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginTop: 10 }}>
              <Btn title="Send test e-mail" kind="secondary" small disabled={!canMail || mailBusy} onPress={() => runMail(onTestMail)} style={{ marginRight: 8, marginTop: 6 }} />
              {onSummaryMail ? (
                <Btn title="E-mail me a health summary now" kind="secondary" small disabled={!canMail || mailBusy} onPress={() => runMail(onSummaryMail)} style={{ marginTop: 6 }} />
              ) : null}
            </View>
          </View>
        )}
        {mailMsg ? <Banner kind={mailMsg.ok ? 'info' : 'danger'}>{mailMsg.text}</Banner> : null}
      </Card>

      {themeSwitchAvailable() ? (
        <Card>
          <H2>Appearance</H2>
          <Segmented
            testID="themeSeg"
            value={THEME_MODE}
            onChange={(m) => m !== THEME_MODE && setThemeMode(m)}
            options={[
              { value: 'light', label: 'Light', icon: 'sun', testID: 'theme_light' },
              { value: 'dark', label: 'Dark', icon: 'moon', testID: 'theme_dark' },
              { value: 'system', label: 'System', icon: 'phone', testID: 'theme_system' },
            ]}
          />
          <Muted style={{ marginTop: 10 }}>
            {(THEME_MODE === 'system' ? 'Following your phone: ' + THEME + ' now. ' : '') + 'Saved on this phone. Switching restarts the replay from its first event, so save other changes first.'}
          </Muted>
        </Card>
      ) : null}

      <Card>
        <H2>Data mode</H2>
        <View style={st.wrap}>
          <Chip label="Replay demo (past data)" active={p.mode === 'replay'} onPress={() => set('mode', 'replay')} />
          <Chip label="Live data" active={p.mode === 'live'} onPress={() => set('mode', 'live')} />
        </View>
        {p.mode === 'replay' ? (
          <View>
            <Text style={st.label}>Replay period</Text>
            {isOffline(p.server) ? <Muted>Built-in demo: 22–25 Apr 2026 (Silk Board pollution event).</Muted> : null}
            <View style={[st.wrap, isOffline(p.server) ? { display: 'none' } : null]}>
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
        {offlineAvailable() ? (
          <Row
            label="Use built-in demo data (no laptop needed)"
            value={isOffline(p.server)}
            onChange={(v) => setP((x) => ({ ...x, server: v ? OFFLINE_SERVER : 'http://', mode: v ? 'replay' : x.mode, period: v ? 'validation' : x.period }))}
          />
        ) : null}
        {isOffline(p.server) ? (
          <Muted>Real forecasts and advice from the project, packed inside the app: 22–25 Apr 2026 at all 8 stations. Live data needs the laptop server: switch this off and enter its address.</Muted>
        ) : (
        <View>
        <Muted>The app reads data from the project's server on your laptop. Phone and laptop must be on the same Wi-Fi or hotspot.</Muted>
        <TextInput
          value={p.server}
          onChangeText={(v) => set('server', v)}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://192.168.1.5:8000"
          placeholderTextColor={C.faint}
          style={[st.input, { marginTop: 10 }]}
        />
        <Btn title={busy ? 'Checking...' : 'Test connection'} kind="secondary" small onPress={testServer} disabled={busy} style={{ marginTop: 10 }} />
        </View>
        )}
        {msg ? <Banner kind={msg.ok ? 'info' : 'danger'}>{msg.text}</Banner> : null}
      </Card>

      <Btn testID="saveProfile" title={welcome ? 'Start' : 'Save'} onPress={() => onSave(p)} style={{ marginBottom: 24 }} />
    </View>
  );
}

function Row({ label, value, onChange }) {
  return (
    <View style={st.row}>
      <Text style={{ flex: 1, color: C.text, fontSize: 15, paddingRight: 10 }}>{label}</Text>
      <Toggle value={value} onValueChange={onChange} label={label} />
    </View>
  );
}

const st = StyleSheet.create({
  welcomeBox: { marginTop: 6, marginBottom: 22, marginHorizontal: -20, paddingHorizontal: 20, paddingTop: 24, overflow: 'hidden', position: 'relative' },
  welcomeOrb: { position: 'absolute', right: -96, top: -46 },
  welcome: { fontFamily: F.serif, fontSize: 44, lineHeight: 50, fontWeight: '600', color: C.text, marginTop: 96, marginBottom: 14, letterSpacing: -1 },
  label: { fontWeight: '600', color: C.soft, marginBottom: 10, fontSize: 14 },
  input: { borderWidth: 1.5, borderColor: C.line, borderRadius: R.md, paddingHorizontal: 16, paddingVertical: 13, fontSize: 16, color: C.text, backgroundColor: C.bg },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  err: { color: C.danger, fontSize: 13, marginTop: 6 },
  ok: { color: C.good, fontSize: 15, fontWeight: '600' },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.line, marginTop: 10 },
});
