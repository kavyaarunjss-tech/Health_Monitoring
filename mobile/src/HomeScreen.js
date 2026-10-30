// Home: current AQI, the next 24 h forecast, a small chart, your top 3 actions and the pollutants.
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, catStyle, pname, fmtTime, fmtHour } from './theme';
import { Card, H2, Muted, Pill, Btn, Banner, ActionRow, Loading } from './ui';

export default function HomeScreen({ vm, loading, error, alertFrom, replay, onOpenAdvice, onOpenStations, onRetry }) {
  return (
    <View>
      {vm && vm.banner ? <ModeBanner banner={vm.banner} /> : null}
      {replay ? <ReplayControls {...replay} /> : null}
      {error ? (
        <Card accent={C.danger}>
          <Text style={st.errTitle}>Could not load data</Text>
          <Muted>{error}</Muted>
          {onRetry ? <Btn title="Try again" small onPress={onRetry} style={{ marginTop: 12, alignSelf: 'flex-start' }} /> : null}
        </Card>
      ) : null}
      {!vm && loading ? <Loading text="Loading air quality..." /> : null}
      {vm ? (
        <View style={loading ? { opacity: 0.6 } : null}>
          {(vm.warnings || []).map((w, i) => (
            <Banner key={i} kind={vm.stale ? 'danger' : 'warn'}>{w}</Banner>
          ))}
          <NowCard vm={vm} onOpenStations={onOpenStations} />
          <ForecastGrid forecasts={vm.forecasts} alertFrom={alertFrom} stale={vm.stale} />
          <Chart vm={vm} />
          <TopActions personal={vm.personal} onOpenAdvice={onOpenAdvice} />
          <Pollutants list={vm.pollutants} />
        </View>
      ) : null}
    </View>
  );
}

function ModeBanner({ banner }) {
  const bg = banner.kind === 'danger' ? C.danger : banner.kind === 'replay' ? '#4a3aa8' : C.teal;
  return (
    <View style={[st.modeBanner, { backgroundColor: bg }]} testID="modeBanner">
      <Text style={st.modeTag}>{banner.tag}</Text>
      <Text style={st.modeText} numberOfLines={2}>{banner.text}</Text>
    </View>
  );
}

function ReplayControls({ playing, onPlay, onStep, onSkip, speed, onSpeed, canBack, canForward, skipMsg }) {
  return (
    <Card style={{ paddingVertical: 12 }}>
      <View style={st.ctrlRow}>
        <CtrlBtn label={'⏮  −1 h'} onPress={() => onStep(-1)} disabled={!canBack} />
        <TouchableOpacity testID="playBtn" accessibilityRole="button" onPress={onPlay} style={st.playBtn} activeOpacity={0.8}>
          <Text style={st.playText}>{playing ? '⏸  Pause' : '▶  Play'}</Text>
        </TouchableOpacity>
        <CtrlBtn label={'+1 h  ⏭'} onPress={() => onStep(1)} disabled={!canForward} />
      </View>
      <View style={[st.ctrlRow, { marginTop: 10 }]}>
        <Text style={st.ctrlLabel}>Speed:</Text>
        {[1, 3, 6].map((v) => (
          <TouchableOpacity key={v} onPress={() => onSpeed(v)} style={[st.speed, speed === v ? st.speedOn : null]}>
            <Text style={[st.speedText, speed === v ? { color: '#fff' } : null]}>{v} h/step</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Btn testID="skipBtn" title="Skip to next pollution event" kind="secondary" small onPress={onSkip} style={{ marginTop: 10 }} />
      {skipMsg ? <Muted style={{ marginTop: 6, textAlign: 'center' }}>{skipMsg}</Muted> : null}
    </Card>
  );
}

function CtrlBtn({ label, onPress, disabled }) {
  return (
    <TouchableOpacity accessibilityRole="button" disabled={disabled} onPress={onPress} style={[st.ctrlBtn, disabled ? { opacity: 0.4 } : null]}>
      <Text style={st.ctrlBtnText}>{label}</Text>
    </TouchableOpacity>
  );
}

function NowCard({ vm, onOpenStations }) {
  const n = vm.now;
  const c = catStyle(n && n.category);
  const head = vm.personal && vm.personal.top3 && vm.personal.top3[0];
  return (
    <View style={[st.now, { backgroundColor: n ? c.bg : '#9aa5b1' }]} testID="nowCard">
      <TouchableOpacity onPress={onOpenStations} accessibilityRole="button">
        <Text style={[st.nowStation, { color: c.fg }]} numberOfLines={1}>{'📍 ' + vm.stationName + '  ▾'}</Text>
      </TouchableOpacity>
      <Text style={[st.nowLabel, { color: c.fg }]}>{vm.nowLabel}</Text>
      {n ? (
        <View style={st.nowRow}>
          <Text style={[st.nowAqi, { color: c.fg }]} testID="nowAqi">{n.aqi}</Text>
          <View style={{ marginLeft: 14, flex: 1 }}>
            <Text style={[st.nowCat, { color: c.fg }]}>{n.category}</Text>
            <Text style={[st.nowSub, { color: c.fg }]}>CPCB AQI{n.dominant ? '  ·  mainly ' + pname(n.dominant) : ''}</Text>
          </View>
        </View>
      ) : (
        <Text style={[st.nowCat, { color: '#fff', marginVertical: 12 }]}>No valid AQI for this hour (data gap)</Text>
      )}
      {head ? (
        <View style={st.nowAdvice}>
          <Text style={st.nowAdviceText} numberOfLines={3}>{head.text}</Text>
        </View>
      ) : null}
    </View>
  );
}

function ForecastGrid({ forecasts, alertFrom, stale }) {
  const main = (forecasts || []).filter((f) => f.horizon <= 24);
  const allPast = main.length > 0 && main.every((f) => f.past);
  return (
    <Card>
      <H2>Next 24 hours</H2>
      {allPast ? (
        <Muted>No forecast for the coming hours: the newest data is too old, so every forecast time (up to 24 h) has already passed.</Muted>
      ) : (
        <View style={st.grid}>
          {main.map((f) => (
            <FcCard key={f.horizon} f={f} alertFrom={alertFrom} />
          ))}
        </View>
      )}
      <Muted style={{ marginTop: 6 }}>
        {stale
          ? 'Forecasts start from the last observation, not from now.'
          : 'Likely range shown under each forecast. +1 and +6 h are the most reliable.'}
      </Muted>
    </Card>
  );
}

function FcCard({ f, alertFrom }) {
  if (!f.available) {
    return (
      <View style={[st.fc, { backgroundColor: '#f1f3f6' }]}>
        <Text style={st.fcH}>+{f.horizon} h</Text>
        <Muted>Not available (data gap)</Muted>
      </View>
    );
  }
  const c = catStyle(f.category);
  const warn = f.aqi >= alertFrom;
  const maybe = !warn && f.range_high >= alertFrom && f.horizon <= 12;
  return (
    <View style={[st.fc, { borderTopColor: c.bg }, f.past ? { opacity: 0.5 } : null]} testID={'fc' + f.horizon}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={st.fcH}>+{f.horizon} h</Text>
        {warn ? <Text style={st.fcWarn}>{'⚠️'}</Text> : maybe ? <Text style={st.fcMaybe}>?</Text> : null}
      </View>
      <Text style={st.fcAqi}>{f.aqi}</Text>
      <Pill category={f.category} small />
      <Text style={st.fcRange}>likely {f.range_low}–{f.range_high}</Text>
      <Text style={st.fcTime}>{f.past ? 'passed · ' : ''}{fmtTime(f.target_end)}</Text>
    </View>
  );
}

function Chart({ vm }) {
  const obs = vm.observed || [];
  const fcs = (vm.forecasts || []).filter((f) => f.available && f.horizon <= 24);
  const vals = obs.map((o) => o.aqi).concat(fcs.map((f) => f.aqi)).filter((v) => v != null);
  if (!vals.length) return null;
  const top = Math.min(500, Math.max(150, Math.max(...vals) * 1.15));
  const H = 130;
  const slots = [];
  const byOff = {};
  obs.forEach((o) => {
    if (o.offset >= -24 && o.offset <= 0) byOff[o.offset] = o;
  });
  const fcBy = {};
  fcs.forEach((f) => (fcBy[f.horizon] = f));
  for (let k = -24; k <= 24; k++) slots.push(k);
  return (
    <Card>
      <H2>Last 24 h and forecast</H2>
      <View style={[st.chart, { height: H }]}>
        {slots.map((k) => {
          const o = byOff[k];
          const f = k > 0 ? fcBy[k] : null;
          const v = o ? o.aqi : f ? f.aqi : null;
          const color = v == null ? 'transparent' : catStyle(o ? o.category : f.category).bg;
          return (
            <View key={k} style={st.slot}>
              {k === 0 ? <View style={st.nowLine} /> : null}
              {v != null ? (
                <View
                  style={[
                    st.bar,
                    { height: Math.max(3, (v / top) * H), backgroundColor: color },
                    f ? { opacity: 0.9, borderWidth: 2, borderColor: C.navy, marginHorizontal: -2 } : null,
                  ]}
                />
              ) : null}
            </View>
          );
        })}
      </View>
      <View style={st.axis}>
        <Text style={st.axisText}>−24 h</Text>
        <Text style={[st.axisText, { fontWeight: '700' }]}>{vm.stale ? 'last data' : 'now'}</Text>
        <Text style={st.axisText}>+24 h</Text>
      </View>
      <Muted style={{ marginTop: 6 }}>Thin bars: measured AQI each hour. Outlined bars: our forecasts at +1, +6, +12 and +24 h.</Muted>
    </Card>
  );
}

function TopActions({ personal, onOpenAdvice }) {
  if (!personal || !personal.top3) return null;
  return (
    <Card accent={C.teal}>
      <H2>Your top 3 actions</H2>
      {personal.top3.map((a, i) => (
        <ActionRow key={i} icon={a.icon} marked={a.marked} text={a.text} source={a.source} />
      ))}
      <Btn title="See all health advice" kind="secondary" small onPress={onOpenAdvice} style={{ marginTop: 10 }} />
    </Card>
  );
}

function Pollutants({ list }) {
  const [open, setOpen] = useState(false);
  if (!list) return null;
  return (
    <Card>
      <TouchableOpacity onPress={() => setOpen(!open)} accessibilityRole="button">
        <H2 right={<Text style={{ color: C.teal, fontWeight: '700' }}>{open ? 'Hide ▴' : 'Show ▾'}</Text>}>Pollutants</H2>
      </TouchableOpacity>
      {open ? (
        <View>
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
              <Muted>
                {p.avg != null ? p.window + ' average ' + p.avg + ' ' + p.unit : ''}
                {p.value != null ? '  ·  now ' + p.value + ' ' + p.unit : ''}
              </Muted>
            </View>
          ))}
          <Muted style={{ marginTop: 8 }}>The AQI is the highest sub-index. Sub-indices use CPCB's 24 h (8 h for O₃, CO) averages.</Muted>
        </View>
      ) : (
        <Muted>Tap to see each pollutant's level.</Muted>
      )}
    </Card>
  );
}

const st = StyleSheet.create({
  errTitle: { fontWeight: '700', fontSize: 16, color: C.danger, marginBottom: 4 },
  modeBanner: { borderRadius: 12, paddingVertical: 10, paddingHorizontal: 14, marginBottom: 12, flexDirection: 'row', alignItems: 'center' },
  modeTag: { color: '#fff', fontWeight: '800', fontSize: 12, letterSpacing: 1, marginRight: 10 },
  modeText: { color: '#fff', fontSize: 14, flex: 1, fontWeight: '600' },
  ctrlRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ctrlBtn: { paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, backgroundColor: '#eef2f6' },
  ctrlBtnText: { color: C.navy, fontWeight: '700', fontSize: 14 },
  playBtn: { backgroundColor: C.teal, borderRadius: 999, paddingVertical: 12, paddingHorizontal: 22 },
  playText: { color: '#fff', fontWeight: '800', fontSize: 16 },
  ctrlLabel: { color: C.muted, fontSize: 13 },
  speed: { paddingVertical: 6, paddingHorizontal: 10, borderRadius: 999, borderWidth: 1, borderColor: C.border },
  speedOn: { backgroundColor: C.navy, borderColor: C.navy },
  speedText: { fontSize: 13, color: C.text },
  now: { borderRadius: 18, padding: 18, marginBottom: 12 },
  nowStation: { fontSize: 15, fontWeight: '700' },
  nowLabel: { fontSize: 13, marginTop: 2, opacity: 0.9 },
  nowRow: { flexDirection: 'row', alignItems: 'center', marginTop: 8 },
  nowAqi: { fontSize: 64, fontWeight: '800', lineHeight: 72 },
  nowCat: { fontSize: 24, fontWeight: '800' },
  nowSub: { fontSize: 13, marginTop: 2, opacity: 0.9 },
  nowAdvice: { backgroundColor: 'rgba(255,255,255,0.92)', borderRadius: 10, padding: 10, marginTop: 12 },
  nowAdviceText: { color: C.text, fontSize: 14, lineHeight: 20 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  fc: {
    width: '48.5%',
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: C.border,
    borderTopWidth: 5,
    borderRadius: 12,
    padding: 10,
    marginBottom: 8,
  },
  fcH: { fontWeight: '700', color: C.muted, fontSize: 13 },
  fcWarn: { fontSize: 16 },
  fcMaybe: { fontSize: 14, fontWeight: '800', color: C.warnText },
  fcAqi: { fontSize: 30, fontWeight: '800', color: C.text, marginVertical: 2 },
  fcRange: { color: C.muted, fontSize: 12, marginTop: 6 },
  fcTime: { color: C.text, fontSize: 12, marginTop: 2 },
  chart: { flexDirection: 'row', alignItems: 'flex-end', borderBottomWidth: 1, borderBottomColor: C.border },
  slot: { flex: 1, height: '100%', justifyContent: 'flex-end', alignItems: 'stretch', marginHorizontal: 0.5 },
  bar: { borderTopLeftRadius: 2, borderTopRightRadius: 2 },
  nowLine: { position: 'absolute', top: 0, bottom: 0, right: -1, width: 2, backgroundColor: C.navy, opacity: 0.6 },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  axisText: { fontSize: 12, color: C.muted },
  pRow: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.border },
  pName: { fontWeight: '700', color: C.text, fontSize: 15 },
  pVal: { color: C.text, fontSize: 14 },
  pTrack: { height: 8, borderRadius: 4, backgroundColor: '#eef2f6', marginVertical: 6, overflow: 'hidden' },
  pFill: { height: 8, borderRadius: 4 },
});
