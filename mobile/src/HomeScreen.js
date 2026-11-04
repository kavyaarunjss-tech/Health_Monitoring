// Home: the AQI now (editorial hero with a lit orb), where it sits on the CPCB scale, an alert strip, the next 24 hours,
// one line "for you", listen/share, and the pollutants behind a toggle.
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, F, R, SH, SH_SM, THEME, catStyle, catText, pname, fmtClock, scalePos, CAT_ORDER } from './theme';
import { Card, Muted, Btn, Banner, Loading, Icon, Rich, Orb, Overline, IconBtn, CatPill, s as ui } from './ui';

export default function HomeScreen({ vm, loading, error, alertFrom, onOpenAdvice, onRetry, onShare, onListen, name }) {
  if (!vm) {
    return (
      <View>
        {error ? <ErrorCard error={error} onRetry={onRetry} /> : null}
        {loading && !error ? <Loading text="Loading air quality..." /> : null}
      </View>
    );
  }
  return (
    <View style={loading ? { opacity: 0.8 } : null}>
      {error ? <ErrorCard error={error} onRetry={onRetry} /> : null}
      {(vm.warnings || []).map((w, i) => (
        <Banner key={i} kind={vm.stale ? 'danger' : 'warn'}>{w}</Banner>
      ))}
      <Text style={st.hello}>{name && name.trim() ? 'Hello, ' + name.trim().split(' ')[0] : 'Hello'}</Text>
      <Text style={st.helloSub}>{vm.mode === 'replay' ? "Today's air, replayed" : "Today's air"}</Text>
      <Hero vm={vm} onShare={onShare} onListen={onListen} />
      <AlertStrip vm={vm} alertFrom={alertFrom} onPress={onOpenAdvice} />
      <Next24 vm={vm} alertFrom={alertFrom} />
      <ForYou personal={vm.personal} onPress={onOpenAdvice} />
      <Pollutants list={vm.pollutants} />
    </View>
  );
}

function ErrorCard({ error, onRetry }) {
  return (
    <Card style={{ backgroundColor: C.dangerBg, shadowOpacity: 0, elevation: 0 }}>
      <Text style={{ color: C.dangerText, fontWeight: '700', fontSize: 16, marginBottom: 4 }}>Could not load data</Text>
      <Text style={{ color: C.dangerText, fontSize: 14, lineHeight: 20 }}>{error}</Text>
      {onRetry ? <Btn title="Try again" small kind="secondary" onPress={onRetry} style={{ marginTop: 12, alignSelf: 'flex-start' }} /> : null}
    </Card>
  );
}

function Hero({ vm, onShare, onListen }) {
  const n = vm.now;
  const c = n ? catStyle(n.category) : null;
  return (
    <View style={st.hero} testID="nowCard">
      <View style={st.blob} pointerEvents="none">
        <Orb color={c ? c.bg : null} size={300} />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Text style={[st.time, { flex: 1 }]} testID="modeBanner" numberOfLines={1}>{vm.timeLine}</Text>
        {onListen ? <IconBtn testID="listenBtn" icon="speaker" label="Listen" onPress={onListen} style={st.heroBtn} /> : null}
        {onShare ? <IconBtn testID="shareBtn" icon="share" label="Share" onPress={onShare} style={[st.heroBtn, { marginLeft: 8 }]} /> : null}
      </View>
      {n ? (
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', marginTop: 10 }}>
            <Text style={st.big} testID="nowAqi">{n.aqi}</Text>
            <View style={{ marginLeft: 12, paddingBottom: 16 }}>
              <Text style={st.aqiLbl}>AQI</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 4 }}>
            <CatPill category={n.category} />
            {n.dominant ? <Text style={st.sub}>{'mainly ' + pname(n.dominant)}</Text> : null}
          </View>
          <ScaleBar aqi={n.aqi} />
        </View>
      ) : (
        <View style={{ marginTop: 14, maxWidth: 260 }}>
          <Text style={[st.cat, { color: C.text }]}>No AQI for this hour</Text>
          <Muted style={{ marginTop: 6 }}>The station has a data gap. Try the next hour or another station.</Muted>
        </View>
      )}
    </View>
  );
}

const SEG = [1, 1, 2, 2, 2, 2]; // CPCB band widths: 0-50, 50-100, 100-200, 200-300, 300-400, 400-500
function ScaleBar({ aqi }) {
  const pos = scalePos(aqi) * 100;
  return (
    <View style={{ marginTop: 18 }} accessibilityLabel={'AQI ' + aqi + ' on the CPCB scale from 0 to 500'}>
      <View style={st.scale}>
        {CAT_ORDER.map((cat, i) => (
          <View
            key={cat}
            style={{
              flex: SEG[i],
              backgroundColor: catStyle(cat).bg,
              marginLeft: i ? 4 : 0,
              borderRadius: 3,
            }}
          />
        ))}
        <View style={[st.marker, { left: pos + '%' }]}>
          <View style={st.markerDot} />
        </View>
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
    <TouchableOpacity onPress={onPress} accessibilityRole="button" activeOpacity={0.85} style={st.alert} testID="alertStrip">
      <View style={st.alertIcon}>
        <Icon name="alert" size={20} color={C.warnText} />
      </View>
      <View style={{ flex: 1, marginHorizontal: 12 }}>
        <Text style={st.alertText}>{text}</Text>
        <Text style={st.alertLink}>See what to do</Text>
      </View>
      <Icon name="arrowRight" size={18} color={C.warnText} />
    </TouchableOpacity>
  );
}

function trendOf(vm) {
  const main = (vm.forecasts || []).filter((f) => f.available && !f.past);
  if (!main.length || !vm.now) return null;
  const last = main[main.length - 1];
  const d = last.aqi - vm.now.aqi;
  if (d <= -10) return { icon: 'down', color: C.good, text: 'Falling to ' + last.aqi };
  if (d >= 10) return { icon: 'up', color: C.warnIcon, text: 'Rising to ' + last.aqi };
  return { icon: 'steady', color: C.muted, text: 'Steady around ' + last.aqi };
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
          <View style={st.trend}>
            <Icon name={tr.icon} size={15} color={tr.color} width={2} />
            <Text style={{ color: tr.color, fontWeight: '600', fontSize: 13, marginLeft: 5 }}>{tr.text}</Text>
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
                <View style={[st.colBar, { height: c.aqi == null ? 8 : Math.max(10, (c.aqi / top) * 60), backgroundColor: c.aqi == null ? C.line : catStyle(c.cat).bg }]} />
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
    <TouchableOpacity onPress={onPress} accessibilityRole="button" activeOpacity={0.85} style={st.forYou} testID="forYou">
      <View style={st.forYouIcon}>
        <Icon name={a.icon || 'info'} size={20} color={C.lavenderText} />
      </View>
      <View style={{ flex: 1, marginHorizontal: 14 }}>
        <Text style={st.forYouKicker}>For you today</Text>
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
        <View style={st.showBtn}><Text style={{ color: C.text, fontWeight: '600', fontSize: 13 }}>{open ? 'Hide' : 'Show'}</Text></View>
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
    <View style={st.playerWrap}>
      {skipMsg ? <Text style={st.skipMsg}>{skipMsg}</Text> : null}
      <View style={st.player}>
        <RoundBtn testID="stepBack" icon="chevronLeft" label="Back 1 hour" onPress={() => onStep(-1)} disabled={!canBack} />
        <TouchableOpacity testID="playBtn" accessibilityRole="button" accessibilityLabel={playing ? 'Pause' : 'Play'} onPress={onPlay} style={st.play}>
          <Icon name={playing ? 'pause' : 'play'} size={18} color={C.onPrimary} />
          <Text style={{ position: 'absolute', opacity: 0, fontSize: 1 }}>{playing ? 'Pause' : 'Play'}</Text>
        </TouchableOpacity>
        <RoundBtn testID="stepFwd" icon="chevronRight" label="Forward 1 hour" onPress={() => onStep(1)} disabled={!canForward} />
        <TouchableOpacity onPress={() => onSpeed(speed === 1 ? 3 : speed === 3 ? 6 : 1)} style={{ flex: 1, marginLeft: 10 }} accessibilityRole="button">
          <Text style={st.playerText} numberOfLines={1}>{clockText}</Text>
          <Text style={st.playerSub}>{speed + ' h per step · tap to change'}</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="skipBtn" onPress={onSkip} accessibilityRole="button" style={st.next}>
          <Text style={{ color: C.lavenderText, fontWeight: '600', fontSize: 13 }}>Next event</Text>
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
  hello: { fontFamily: F.display, color: C.text, fontSize: 32, fontWeight: '400', letterSpacing: -1, lineHeight: 38, marginTop: 6 },
  helloSub: { fontFamily: F.display, color: C.muted, fontSize: 32, fontWeight: '400', letterSpacing: -1, lineHeight: 38, marginBottom: 18 },
  hero: { backgroundColor: C.card, borderRadius: R.xl, padding: 20, marginBottom: 14, overflow: 'hidden', position: 'relative', ...SH },
  blob: { position: 'absolute', right: -110, top: -120 },
  heroBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.card2, shadowOpacity: 0, elevation: 0 },
  time: { color: C.muted, fontSize: 13, fontWeight: '500' },
  big: { fontFamily: F.display, color: C.text, fontSize: 96, fontWeight: '300', letterSpacing: -5, lineHeight: 100 },
  aqiLbl: { color: C.muted, fontSize: 15, fontWeight: '600' },
  cat: { fontFamily: F.display, fontSize: 22, fontWeight: '600', letterSpacing: -0.4 },
  sub: { color: C.muted, fontSize: 14, marginLeft: 10 },
  scale: { flexDirection: 'row', height: 6, position: 'relative' },
  marker: { position: 'absolute', top: -6, width: 18, height: 18, marginLeft: -9, borderRadius: 9, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', ...SH_SM },
  markerDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.text },
  scaleLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 },
  scaleText: { color: C.faint, fontSize: 11 },
  alert: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.warnBg, borderRadius: R.xl, paddingVertical: 14, paddingHorizontal: 14, marginBottom: 24 },
  alertIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: THEME === 'light' ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.06)', alignItems: 'center', justifyContent: 'center' },
  alertText: { color: C.warnText, fontSize: 14, lineHeight: 20 },
  alertLink: { color: C.warnText, fontSize: 14, fontWeight: '700', marginTop: 2 },
  secHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  trend: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: R.pill, paddingHorizontal: 12, height: 32, ...SH_SM },
  bars: { flexDirection: 'row', backgroundColor: C.card, borderRadius: R.xl, paddingTop: 16, paddingBottom: 12, paddingHorizontal: 8, alignItems: 'flex-end', marginBottom: 14, ...SH_SM },
  col: { flex: 1, alignItems: 'center' },
  colAqi: { color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 8 },
  colBarWrap: { width: 30, height: 70, alignItems: 'center', justifyContent: 'flex-end', borderRadius: 15, paddingBottom: 4, backgroundColor: C.card2 },
  colNow: { borderWidth: 2, borderColor: C.text, backgroundColor: 'transparent' },
  colBar: { width: 22, borderRadius: 11 },
  colLabel: { color: C.soft, fontSize: 12, fontWeight: '600', marginTop: 10 },
  colTime: { color: C.faint, fontSize: 11, marginTop: 2 },
  warnDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.warnIcon, marginTop: 6 },
  forYou: { flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: R.xl, padding: 16, marginBottom: 14, ...SH_SM },
  forYouIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: C.lavender, alignItems: 'center', justifyContent: 'center' },
  forYouKicker: { color: C.muted, fontSize: 12, fontWeight: '500' },
  forYouText: { color: C.text, fontSize: 15, fontWeight: '600', lineHeight: 21, marginTop: 2 },
  showBtn: { backgroundColor: C.card2, borderRadius: R.pill, paddingHorizontal: 14, height: 32, justifyContent: 'center' },
  pRow: { paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.line },
  pName: { fontWeight: '600', color: C.text, fontSize: 15 },
  pVal: { color: C.soft, fontSize: 14 },
  pTrack: { height: 6, borderRadius: 3, backgroundColor: C.card2, marginVertical: 8, overflow: 'hidden' },
  pFill: { height: 6, borderRadius: 3 },
  playerWrap: { marginHorizontal: 16, marginBottom: 8, backgroundColor: C.card, borderRadius: R.pill, ...SH },
  player: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 8 },
  play: { width: 48, height: 48, borderRadius: 24, backgroundColor: C.primary, alignItems: 'center', justifyContent: 'center', marginHorizontal: 6 },
  round: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.card2, alignItems: 'center', justifyContent: 'center' },
  playerText: { color: C.text, fontSize: 13, fontWeight: '600' },
  playerSub: { color: C.faint, fontSize: 11, marginTop: 2 },
  next: { height: 40, justifyContent: 'center', paddingHorizontal: 14, borderRadius: R.pill, backgroundColor: C.lavender, marginLeft: 6 },
  skipMsg: { color: C.muted, fontSize: 12, textAlign: 'center', paddingHorizontal: 16, paddingTop: 10 },
});
