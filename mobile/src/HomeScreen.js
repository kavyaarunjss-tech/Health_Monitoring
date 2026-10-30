// Home: the AQI now (big), where it sits on the CPCB scale, an alert strip, the next 24 hours and one line "for you".
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, catStyle, pname, fmtClock, scalePos, CAT_ORDER } from './theme';
import { Card, Muted, Btn, Banner, Loading, Icon, Rich, s as ui } from './ui';

export default function HomeScreen({ vm, loading, error, alertFrom, onOpenAdvice, onRetry }) {
  if (!vm) {
    return (
      <View>
        {error ? <ErrorCard error={error} onRetry={onRetry} /> : null}
        {loading && !error ? <Loading text="Loading air quality..." /> : null}
      </View>
    );
  }
  return (
    <View style={loading ? { opacity: 0.75 } : null}>
      {error ? <ErrorCard error={error} onRetry={onRetry} /> : null}
      {(vm.warnings || []).map((w, i) => (
        <Banner key={i} kind={vm.stale ? 'danger' : 'warn'}>{w}</Banner>
      ))}
      <Text style={st.time} testID="modeBanner">{vm.timeLine}</Text>
      <BigNumber vm={vm} />
      {vm.now ? <ScaleBar aqi={vm.now.aqi} /> : null}
      <AlertStrip vm={vm} alertFrom={alertFrom} onPress={onOpenAdvice} />
      <Next24 vm={vm} alertFrom={alertFrom} />
      <ForYou personal={vm.personal} onPress={onOpenAdvice} />
      <Pollutants list={vm.pollutants} />
    </View>
  );
}

function ErrorCard({ error, onRetry }) {
  return (
    <Card style={{ backgroundColor: C.dangerBg }}>
      <Text style={{ color: '#ffd0d2', fontWeight: '700', fontSize: 16, marginBottom: 4 }}>Could not load data</Text>
      <Text style={{ color: '#ffd0d2', fontSize: 14, lineHeight: 20 }}>{error}</Text>
      {onRetry ? <Btn title="Try again" small kind="secondary" onPress={onRetry} style={{ marginTop: 12, alignSelf: 'flex-start' }} /> : null}
    </Card>
  );
}

function BigNumber({ vm }) {
  const n = vm.now;
  if (!n) {
    return (
      <View style={{ marginVertical: 12 }}>
        <Text style={[st.cat, { color: C.muted }]}>No AQI for this hour</Text>
        <Muted>The station has a data gap. Try the next hour or another station.</Muted>
      </View>
    );
  }
  const c = catStyle(n.category);
  return (
    <View style={st.bigRow} testID="nowCard">
      <Text style={st.big} testID="nowAqi">{n.aqi}</Text>
      <View style={{ marginLeft: 14, paddingBottom: 10, flex: 1 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: c.bg, marginRight: 8 }} />
          <Text style={[st.cat, { color: c.bg }]}>{n.category}</Text>
        </View>
        <Text style={st.sub}>{'CPCB AQI' + (n.dominant ? ' · mainly ' + pname(n.dominant) : '')}</Text>
      </View>
    </View>
  );
}

const SEG = [1, 1, 2, 2, 2, 2]; // CPCB band widths: 0-50, 50-100, 100-200, 200-300, 300-400, 400-500
function ScaleBar({ aqi }) {
  const pos = scalePos(aqi) * 100;
  return (
    <View style={{ marginTop: 4, marginBottom: 16 }} accessibilityLabel={'AQI ' + aqi + ' on the CPCB scale from 0 to 500'}>
      <View style={st.scale}>
        {CAT_ORDER.map((cat, i) => (
          <View
            key={cat}
            style={{
              flex: SEG[i],
              backgroundColor: catStyle(cat).bg,
              marginLeft: i ? 3 : 0,
              borderTopLeftRadius: i === 0 ? 4 : 0,
              borderBottomLeftRadius: i === 0 ? 4 : 0,
              borderTopRightRadius: i === 5 ? 4 : 0,
              borderBottomRightRadius: i === 5 ? 4 : 0,
            }}
          />
        ))}
        <View style={[st.marker, { left: pos + '%' }]} />
      </View>
      <View style={st.scaleLabels}>
        {['0', '100', '200', '300', '400', '500'].map((l) => (
          <Text key={l} style={st.scaleText}>{l}</Text>
        ))}
      </View>
    </View>
  );
}

function AlertStrip({ vm, alertFrom, onPress }) {
  const main = (vm.forecasts || []).filter((f) => f.available && !f.past);
  const nowOver = vm.now && vm.now.aqi >= alertFrom;
  const first = main.find((f) => f.aqi >= alertFrom);
  if (!nowOver && !first) return null;
  const text = nowOver
    ? 'Above your alert level (' + alertFrom + ').'
    : 'Expected to reach your alert level (' + alertFrom + ') around ' + fmtClock(first.target_end, vm.clock) + '.';
  return (
    <TouchableOpacity onPress={onPress} accessibilityRole="button" activeOpacity={0.8} style={st.alert} testID="alertStrip">
      <Icon name="alert" size={20} color={C.warnIcon} />
      <Text style={st.alertText}>
        {text + ' '}
        <Text style={{ color: '#ffffff', fontWeight: '700' }}>See what to do</Text>
      </Text>
      <Icon name="chevronRight" size={18} color={C.warnText} />
    </TouchableOpacity>
  );
}

function trendOf(vm) {
  const main = (vm.forecasts || []).filter((f) => f.available && !f.past);
  if (!main.length || !vm.now) return null;
  const last = main[main.length - 1];
  const d = last.aqi - vm.now.aqi;
  if (d <= -10) return { icon: 'down', color: C.good, text: 'falling to ' + last.aqi };
  if (d >= 10) return { icon: 'up', color: C.warnIcon, text: 'rising to ' + last.aqi };
  return { icon: 'steady', color: C.muted, text: 'steady around ' + last.aqi };
}

function Next24({ vm, alertFrom }) {
  const main = (vm.forecasts || []).filter((f) => f.horizon <= 24);
  const allPast = main.length > 0 && main.every((f) => f.past);
  const tr = trendOf(vm);
  const cols = [];
  if (vm.now) cols.push({ key: 'now', label: vm.stale ? 'Last' : 'Now', time: fmtClock(vm.clock), aqi: vm.now.aqi, cat: vm.now.category, now: true });
  main.forEach((f) =>
    cols.push({
      key: 'h' + f.horizon,
      label: '+' + f.horizon + ' h',
      time: f.available ? fmtClock(f.target_end, vm.clock) : '',
      aqi: f.available ? f.aqi : null,
      cat: f.category,
      past: f.past,
      warn: f.available && f.aqi >= alertFrom,
      range: f.available ? f.range_low + '–' + f.range_high : '',
    }),
  );
  const top = Math.max(150, ...cols.map((c) => c.aqi || 0));
  return (
    <View style={{ marginBottom: 12 }}>
      <View style={st.secHead}>
        <Text style={ui.h2}>Next 24 hours</Text>
        {tr && !allPast ? (
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Icon name={tr.icon} size={16} color={tr.color} width={2.2} />
            <Text style={{ color: tr.color, fontWeight: '600', fontSize: 14, marginLeft: 4 }}>{tr.text}</Text>
          </View>
        ) : null}
      </View>
      {allPast ? (
        <Card>
          <Muted>No forecast for the coming hours: the newest data is too old, so every forecast time has already passed.</Muted>
        </Card>
      ) : (
        <View style={st.bars}>
          {cols.map((c) => (
            <View key={c.key} style={[st.col, c.past ? { opacity: 0.4 } : null]} testID={c.key === 'now' ? 'colNow' : 'fc' + c.key.slice(1)}>
              <Text style={st.colAqi}>{c.aqi == null ? '–' : c.aqi}</Text>
              <View style={[st.colBarWrap, c.now ? st.colNow : null]}>
                <View style={[st.colBar, { height: c.aqi == null ? 6 : Math.max(8, (c.aqi / top) * 84), backgroundColor: c.aqi == null ? C.card2 : catStyle(c.cat).bg }]} />
              </View>
              <Text style={[st.colLabel, c.now ? { color: C.text } : null]}>{c.label}</Text>
              <Text style={st.colTime} numberOfLines={1}>{c.past ? 'passed' : c.time}</Text>
              <View style={[st.warnDot, c.warn ? null : { backgroundColor: 'transparent' }]} />
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function ForYou({ personal, onPress }) {
  const a = personal && personal.top3 && personal.top3[0];
  if (!a) return null;
  return (
    <TouchableOpacity onPress={onPress} accessibilityRole="button" activeOpacity={0.8} style={st.forYou} testID="forYou">
      <View style={st.forYouIcon}>
        <Icon name={a.icon || 'info'} size={20} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={st.forYouKicker}>For you</Text>
        <Text style={st.forYouText} numberOfLines={2}>{a.text}</Text>
      </View>
      <Icon name="chevronRight" size={18} color={C.faint} />
    </TouchableOpacity>
  );
}

function Pollutants({ list }) {
  const [open, setOpen] = useState(false);
  if (!list) return null;
  return (
    <Card>
      <TouchableOpacity onPress={() => setOpen(!open)} accessibilityRole="button" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={ui.h2}>Pollutants</Text>
        <Text style={{ color: C.accent, fontWeight: '700' }}>{open ? 'Hide' : 'Show'}</Text>
      </TouchableOpacity>
      {open ? (
        <View style={{ marginTop: 6 }}>
          {list.map((p) => (
            <View key={p.key} style={st.pRow}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={st.pName}>{p.label}</Text>
                <Text style={st.pVal}>{p.si != null ? 'sub-index ' + p.si : 'no data'}</Text>
              </View>
              <View style={st.pTrack}>
                {p.si != null ? (
                  <View style={[st.pFill, { width: Math.min(100, (p.si / 500) * 100) + '%', backgroundColor: catStyle(p.category).bg }]} />
                ) : null}
              </View>
              <Text style={ui.src}>
                {(p.avg != null ? p.window + ' average ' + p.avg + ' ' + p.unit : '') + (p.value != null ? '  ·  now ' + p.value + ' ' + p.unit : '')}
              </Text>
            </View>
          ))}
          <Text style={[ui.src, { marginTop: 8 }]}>The AQI is the highest sub-index (CPCB 24 h averages; 8 h for O₃ and CO).</Text>
        </View>
      ) : null}
    </Card>
  );
}

// small player shown above the menu in replay mode
export function ReplayBar({ playing, onPlay, onStep, onSkip, speed, onSpeed, canBack, canForward, skipMsg, clockText }) {
  return (
    <View>
      {skipMsg ? <Text style={st.skipMsg}>{skipMsg}</Text> : null}
      <View style={st.player}>
        <RoundBtn testID="stepBack" icon="chevronLeft" label="Back 1 hour" onPress={() => onStep(-1)} disabled={!canBack} />
        <TouchableOpacity testID="playBtn" accessibilityRole="button" accessibilityLabel={playing ? 'Pause' : 'Play'} onPress={onPlay} style={st.play}>
          <Icon name={playing ? 'pause' : 'play'} size={18} color={C.bg} />
          <Text style={{ position: 'absolute', opacity: 0, fontSize: 1 }}>{playing ? 'Pause' : 'Play'}</Text>
        </TouchableOpacity>
        <RoundBtn testID="stepFwd" icon="chevronRight" label="Forward 1 hour" onPress={() => onStep(1)} disabled={!canForward} />
        <TouchableOpacity onPress={() => onSpeed(speed === 1 ? 3 : speed === 3 ? 6 : 1)} style={{ flex: 1, marginLeft: 10 }} accessibilityRole="button">
          <Text style={st.playerText} numberOfLines={1}>{clockText}</Text>
          <Text style={st.playerSub}>{speed + ' h per step · tap to change'}</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="skipBtn" onPress={onSkip} accessibilityRole="button" style={st.next}>
          <Text style={{ color: C.accent, fontWeight: '700', fontSize: 13 }}>Next event</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function RoundBtn({ icon, label, onPress, disabled, testID }) {
  return (
    <TouchableOpacity testID={testID} accessibilityRole="button" accessibilityLabel={label} onPress={onPress} disabled={disabled} style={[st.round, disabled ? { opacity: 0.35 } : null]}>
      <Icon name={icon} size={18} />
    </TouchableOpacity>
  );
}

const st = StyleSheet.create({
  time: { color: C.muted, fontSize: 14, marginTop: 2 },
  bigRow: { flexDirection: 'row', alignItems: 'flex-end', marginTop: 2 },
  big: { color: C.text, fontSize: 100, fontWeight: '800', letterSpacing: -4, lineHeight: 104 },
  cat: { fontSize: 24, fontWeight: '700' },
  sub: { color: C.muted, fontSize: 13, marginTop: 4 },
  scale: { flexDirection: 'row', height: 8, position: 'relative' },
  marker: { position: 'absolute', top: -5, width: 4, height: 18, marginLeft: -2, borderRadius: 2, backgroundColor: C.text, borderWidth: 1, borderColor: C.bg },
  scaleLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  scaleText: { color: C.faint, fontSize: 11 },
  alert: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.warnBg, borderRadius: 16, paddingVertical: 12, paddingHorizontal: 14, marginBottom: 16 },
  alertText: { flex: 1, color: C.warnText, fontSize: 14, lineHeight: 19, marginHorizontal: 10 },
  secHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  bars: { flexDirection: 'row', backgroundColor: C.card, borderRadius: 20, paddingTop: 14, paddingBottom: 12, paddingHorizontal: 6, alignItems: 'flex-end' },
  col: { flex: 1, alignItems: 'center' },
  colAqi: { color: C.text, fontSize: 14, fontWeight: '800', marginBottom: 6 },
  colBarWrap: { width: 30, height: 92, alignItems: 'center', justifyContent: 'flex-end', borderRadius: 15, paddingBottom: 4 },
  colNow: { borderWidth: 2, borderColor: C.text },
  colBar: { width: 20, borderRadius: 10 },
  colLabel: { color: C.soft, fontSize: 12, fontWeight: '600', marginTop: 8 },
  colTime: { color: C.faint, fontSize: 11, marginTop: 2 },
  warnDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.warnIcon, marginTop: 5 },
  forYou: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: 18, padding: 14, marginBottom: 12 },
  forYouIcon: { width: 40, height: 40, borderRadius: 12, backgroundColor: C.card2, alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  forYouKicker: { color: C.muted, fontSize: 12, fontWeight: '600' },
  forYouText: { color: C.text, fontSize: 14, fontWeight: '600', lineHeight: 19, marginTop: 2 },
  pRow: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.card2 },
  pName: { fontWeight: '700', color: C.text, fontSize: 15 },
  pVal: { color: C.soft, fontSize: 14 },
  pTrack: { height: 6, borderRadius: 3, backgroundColor: C.card2, marginVertical: 6, overflow: 'hidden' },
  pFill: { height: 6, borderRadius: 3 },
  player: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 8 },
  play: { width: 46, height: 46, borderRadius: 23, backgroundColor: C.text, alignItems: 'center', justifyContent: 'center', marginHorizontal: 6 },
  round: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.card2, alignItems: 'center', justifyContent: 'center' },
  playerText: { color: C.text, fontSize: 13, fontWeight: '600' },
  playerSub: { color: C.faint, fontSize: 11, marginTop: 1 },
  next: { height: 44, justifyContent: 'center', paddingLeft: 8 },
  skipMsg: { color: C.muted, fontSize: 12, textAlign: 'center', paddingHorizontal: 16, paddingTop: 6 },
});
