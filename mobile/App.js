// AQ Health: phone app for the Integrated Air Quality and Health Risk Prediction Framework.
// All data, forecasts and health advice come from the project's FastAPI backend on the laptop (backend/app.py);
// the app adds the phone screens, the replay player, the alert pop-up and phone notifications.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, LogBox, RefreshControl } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { C, HOUR, toMs, labelFromMs, fmtTime, fmtDay, fmtClock, catOf, catRank, alertLevel, stationShort, pname, GROUPS } from './src/theme';
import { api, setServer, getServer, guessServer } from './src/api';
import { loadAll, saveAll } from './src/store';
import { initNotifications, notify, askPermission } from './src/notify';
import HomeScreen, { ReplayBar } from './src/HomeScreen';
import AdviceScreen from './src/AdviceScreen';
import StationsScreen from './src/StationsScreen';
import WeekScreen from './src/WeekScreen';
import ProfileScreen from './src/ProfileScreen';
import AlertModal from './src/AlertModal';
import { Loading, Banner, Icon } from './src/ui';

LogBox.ignoreLogs(['expo-notifications', 'Android Push notifications', 'remote notifications']);

const DEFAULT_PROFILE = {
  name: '',
  station: 'silkboard',
  groups: [],
  alertOverride: null,
  notify: true,
  pauseOnAlert: true,
  mode: 'replay',
  period: 'validation',
  server: '',
};
const RANK = { possible: 1, likely: 2 };
const COOLDOWN_MS = 12 * HOUR;
const TICK_MS = 1100;

const TABS = [
  { id: 'home', label: 'Home', icon: 'home' },
  { id: 'advice', label: 'Advice', icon: 'heart' },
  { id: 'stations', label: 'Stations', icon: 'pin' },
  { id: 'week', label: 'Week', icon: 'calendar' },
];

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

function Main() {
  const insets = useSafeAreaInsets();
  const [booted, setBooted] = useState(false);
  const [profile, setProfile] = useState(null);
  const [welcome, setWelcome] = useState(null); // draft profile for first start
  const [tab, setTab] = useState('home');
  const [meta, setMeta] = useState(null);

  // replay
  const [hours, setHours] = useState([]);
  const [idx, setIdx] = useState(-1);
  const [events, setEvents] = useState([]);
  const [st, setSt] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [skipMsg, setSkipMsg] = useState(null);
  // live
  const [live, setLive] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [alert, setAlert] = useState(null);
  const [recent, setRecent] = useState(null); // last alert when pause-on-alert is off
  const [stations, setStations] = useState({ data: null, error: null });
  const [week, setWeek] = useState({ data: null, error: null });
  const [toast, setToast] = useState(null);
  const [reload, setReload] = useState(0);

  const reqId = useRef(0);
  const lastAlert = useRef(null);
  const prevLabel = useRef(null);
  const setupKey = useRef(null);
  const scrollRef = useRef(null);

  const mode = profile ? profile.mode : 'replay';
  const groups = profile ? profile.groups : [];
  const groupsKey = groups.join(',');
  const alertFrom = profile ? alertLevel(profile) : 201;
  const label = idx >= 0 ? hours[idx] : null;

  // ---------------------------------------------------------------- start-up: saved profile or welcome screen
  useEffect(() => {
    (async () => {
      await initNotifications();
      const saved = await loadAll();
      if (saved && saved.profile) {
        const p = { ...DEFAULT_PROFILE, ...saved.profile };
        if (!p.server) p.server = guessServer();
        setServer(p.server);
        setProfile(p);
      } else {
        const p = { ...DEFAULT_PROFILE, server: guessServer() };
        setServer(p.server);
        setWelcome(p);
      }
      setBooted(true);
    })();
  }, []);

  useEffect(() => {
    if (!profile) return;
    api.meta().then(setMeta).catch(() => {});
  }, [profile && profile.server, reload]);

  const showToast = (t) => {
    setToast(t);
    setTimeout(() => setToast(null), 3500);
  };

  // ---------------------------------------------------------------- replay: load hours + events, pick the start hour
  useEffect(() => {
    if (!profile || profile.mode !== 'replay') return;
    const key = [profile.server, profile.period].join('|');
    const keep = setupKey.current === key ? label : null; // same period: stay at the same time (station / profile change)
    setupKey.current = key;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPlaying(false);
    setSkipMsg(null);
    Promise.all([api.hours(profile.period, profile.station), api.events(profile.period, profile.station, alertFrom)])
      .then(([h, ev]) => {
        if (cancelled) return;
        const list = h.hours || [];
        let i = 0;
        if (keep) {
          i = list.findIndex((x) => x >= keep);
          if (i < 0) i = list.length - 1;
        } else {
          const j = pickJump(list, ev.onsets || [], null);
          if (j != null) i = j;
          prevLabel.current = null;
        }
        lastAlert.current = null;
        setEvents(ev.onsets || []);
        setHours(list);
        setIdx(list.length ? i : -1);
        if (!list.length) {
          setLoading(false);
          setError('No replay data for this station and period.');
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setLoading(false);
        setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [profile && profile.mode, profile && profile.station, profile && profile.period, profile && profile.server, alertFrom, reload]);

  // ---------------------------------------------------------------- replay: load the state of the current hour
  useEffect(() => {
    if (!profile || profile.mode !== 'replay' || idx < 0 || !hours[idx]) return;
    const id = ++reqId.current;
    const t = hours[idx];
    setLoading(true);
    api
      .replayState(profile.period, profile.station, t, groups, alertFrom)
      .then((s) => {
        if (id !== reqId.current) return; // an older request: drop it
        const forward = prevLabel.current != null && t > prevLabel.current;
        prevLabel.current = t;
        setSt(s);
        setError(null);
        setLoading(false);
        if (forward) checkAlert(s);
      })
      .catch((e) => {
        if (id !== reqId.current) return;
        setError(e.message);
        setLoading(false);
        setPlaying(false);
      });
  }, [idx, hours, groupsKey, alertFrom]);

  // ---------------------------------------------------------------- replay: playback (next step only after the last one is shown)
  useEffect(() => {
    if (!playing || loading || alert || idx < 0) return;
    if (idx >= hours.length - 1) {
      setPlaying(false);
      return;
    }
    const tm = setTimeout(() => setIdx(stepIndex(hours, idx, speed)), TICK_MS);
    return () => clearTimeout(tm);
  }, [playing, loading, alert, st, idx, hours, speed]);

  // ---------------------------------------------------------------- live mode
  const loadLive = useCallback(async () => {
    if (!profile) return;
    setLoading(true);
    setError(null);
    try {
      const s = await api.liveState(profile.station);
      let personal = null;
      if (s.last_aqi != null) {
        const fcs = (s.forecasts || []).filter((f) => f.horizon <= 24);
        const r = await api.liveAdvice(s.last_aqi, {
          groups: profile.groups,
          alert_from: alertLevel(profile),
          forecasts: fcs,
          now_aqi: s.last_aqi,
          dominant: s.dominant_now,
          station: profile.station,
          last_obs_end: s.last_obs_end,
        });
        personal = r.personal;
      }
      setLive({ s, personal });
    } catch (e) {
      setLive(null);
      setError(
        e.status && e.status >= 500
          ? 'Live data is not set up on this laptop (the live database data/aqi.db is missing), and the government data feed for these stations stopped on 13 Oct 2026. Use the Replay demo (Profile → Data mode).'
          : e.message,
      );
    }
    setLoading(false);
  }, [profile]);

  useEffect(() => {
    if (profile && profile.mode === 'live') {
      setPlaying(false);
      loadLive();
    }
  }, [profile && profile.mode, profile && profile.station, profile && profile.server, groupsKey, alertFrom, reload]);

  // ---------------------------------------------------------------- stations + week tabs
  useEffect(() => {
    if (!profile || tab !== 'stations') return;
    if (mode === 'replay' && !label) return;
    api
      .stationsNow(mode, mode === 'replay' ? label : '')
      .then((d) => setStations({ data: d, error: null }))
      .catch((e) => setStations({ data: null, error: e.status >= 500 && mode === 'live' ? 'Live data is not set up on this laptop. Use the Replay demo.' : e.message }));
  }, [tab, label, mode, reload]);

  useEffect(() => {
    if (!profile || tab !== 'week') return;
    if (mode === 'replay' && !label) return;
    api
      .weekly(profile.station, mode, mode === 'replay' ? label : '', groups)
      .then((d) => setWeek({ data: d, error: null }))
      .catch((e) => setWeek({ data: null, error: e.status >= 404 && mode === 'live' ? 'No live data for this station on this laptop. Use the Replay demo.' : e.message }));
  }, [tab, label, mode, profile && profile.station, groupsKey, reload]);

  // ---------------------------------------------------------------- alerts (same rules as the website)
  function checkAlert(s) {
    if (!profile) return;
    let best = null;
    (s.forecasts || []).forEach((f) => {
      if (!f.available) return;
      const l = f.aqi >= alertFrom ? 'likely' : f.range_high >= alertFrom ? 'possible' : 'none';
      if (l === 'none' || (l === 'likely' && f.horizon > 24) || (l === 'possible' && f.horizon > 12)) return;
      if (!best || RANK[l] > RANK[best.level] || (l === best.level && f.aqi > best.f.aqi)) best = { level: l, f };
    });
    if (!best) return;
    const f = best.f;
    const rank = best.level === 'likely' ? catRank(f.category) : catRank(f.category_high); // what this alert warns about
    const simMs = toMs(s.sim_time_end);
    const last = lastAlert.current;
    let escalation = null;
    if (last && last.station === s.station && simMs >= last.ms && simMs - last.ms < COOLDOWN_MS) {
      if (best.level === 'likely' && rank > last.rank) escalation = 'higher category';
      else if (best.level === 'likely' && last.level === 'possible') escalation = 'higher alert level';
      else return; // cooldown: no repeat alert within 12 simulated hours
    }
    lastAlert.current = { station: s.station, ms: simMs, level: best.level, rank: Math.max(rank, escalation && last ? last.rank : rank) };
    const likely = best.level === 'likely';
    const title = likely ? 'Air quality alert' : 'Possible air quality alert';
    const a = {
      level: best.level,
      f,
      escalation,
      title,
      stationName: s.station_name,
      issued: s.sim_time_end,
      alertFrom,
      lines: (s.personal && s.personal.short) || [],
      actions: (s.personal && s.personal.top3) || [],
    };
    const body =
      (likely
        ? 'Forecast AQI ' + f.aqi + ' (' + f.category + ')'
        : 'Forecast AQI ' + f.aqi + ', could reach ' + f.range_high + ' (' + f.category_high + ')') +
      ' for ' + fmtTime(f.target_end) + ' (+' + f.horizon + ' h)' + (f.dominant ? ', mainly ' + pname(f.dominant) : '') + '. ' +
      (s.personal && s.personal.top3 && s.personal.top3[0] ? s.personal.top3[0].text : '');
    if (profile.notify) notify('[REPLAY DEMO] ' + (escalation ? 'UPDATE: ' : '') + title + ' · ' + stationShort(s.station), body);
    if (profile.pauseOnAlert) {
      setPlaying(false);
      setAlert(a);
    } else {
      setRecent(a);
    }
  }

  // ---------------------------------------------------------------- actions
  const onPlay = () => {
    setSkipMsg(null);
    setRecent(null);
    if (!playing && idx >= hours.length - 1) return;
    setPlaying(!playing);
  };
  const onStep = (dir) => {
    setPlaying(false);
    setSkipMsg(null);
    setIdx(stepIndex(hours, idx, dir));
  };
  const onSkip = () => {
    setPlaying(false);
    const j = pickJump(hours, events, label);
    if (j == null) setSkipMsg('No more pollution events in this period at this station.');
    else {
      setSkipMsg('Jumped to 6 hours before the next pollution event. Press Play.');
      setIdx(j);
    }
  };

  const pickStation = (id) => {
    if (!profile) return;
    const p = { ...profile, station: id };
    setProfile(p);
    saveAll({ profile: p });
    setTab('home');
    if (scrollRef.current && scrollRef.current.scrollTo) scrollRef.current.scrollTo({ y: 0, animated: false });
  };

  const saveProfile = async (p) => {
    setServer(p.server);
    if (p.notify) askPermission();
    setProfile(p);
    setWelcome(null);
    await saveAll({ profile: p });
    setTab('home');
    if (profile) showToast('Saved');
  };

  const testServer = async (url) => {
    const old = getServer();
    setServer(url);
    try {
      const r = await api.ping();
      return { ok: true, text: 'Connected to ' + getServer() + ' (' + r.length + ' stations).' };
    } catch (e) {
      setServer(old);
      return { ok: false, text: e.message };
    }
  };

  const testNotification = async () => {
    const ok = await notify('Test notification', 'AQ Health alerts will look like this. Not medical advice.');
    showToast(ok ? 'Test notification sent' : 'Notifications are not allowed. Allow them in the phone settings.');
  };

  // ---------------------------------------------------------------- view model shared by Home and Advice
  const vm = mode === 'replay' ? (st ? fromReplay(st) : null) : live ? fromLive(live) : null;

  if (!booted) {
    return (
      <View style={[styles.root, { paddingTop: insets.top }]}>
        <Loading text="Starting..." />
      </View>
    );
  }

  const goTab = (id) => {
    setTab(id);
    if (scrollRef.current && scrollRef.current.scrollTo) scrollRef.current.scrollTo({ y: 0, animated: false });
  };
  const groupsLabel = groups.length ? groups.map((g) => (GROUPS.find((x) => x.id === g) || { label: g }).label).join(', ') : 'healthy adult';

  return (
    <View style={styles.root}>
      <StatusBar style="light" />
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        {welcome ? (
          <Text style={styles.appName}>AQ Health</Text>
        ) : (
          <TouchableOpacity testID="stationBtn" accessibilityRole="button" onPress={() => goTab('stations')} style={styles.stationBtn}>
            <Icon name="pin" size={18} color={C.muted} />
            <Text style={styles.stationText} numberOfLines={1}>{stationShort(profile.station)}</Text>
            <Icon name="chevronDown" size={16} color={C.muted} />
          </TouchableOpacity>
        )}
        <View style={{ flex: 1 }} />
        {profile ? (
          <View style={styles.modeChip}>
            <Text style={styles.modeChipText}>{mode === 'replay' ? 'REPLAY' : 'LIVE'}</Text>
          </View>
        ) : null}
        {!welcome ? (
          <TouchableOpacity testID="tab_profile" accessibilityRole="button" accessibilityLabel="Profile and settings" onPress={() => goTab('profile')} style={[styles.gear, tab === 'profile' ? { backgroundColor: C.selBg } : null]}>
            <Icon name="settings" size={20} color={tab === 'profile' ? C.text : C.muted} />
          </TouchableOpacity>
        ) : null}
      </View>

      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 4, paddingBottom: 24 }}
        refreshControl={<RefreshControl refreshing={false} tintColor={C.accent} onRefresh={() => setReload((x) => x + 1)} />}
      >
        {welcome ? (
          <ProfileScreen initial={welcome} welcome onSave={saveProfile} onTestServer={testServer} onTestNotification={testNotification} />
        ) : (
          <View>
            {recent && tab === 'home' ? (
              <Banner kind="warn">
                {'Alert: forecast AQI ' + recent.f.aqi + ' (' + recent.f.category + ') for ' + fmtTime(recent.f.target_end) + ' (+' + recent.f.horizon + ' h).'}
              </Banner>
            ) : null}
            {tab === 'home' ? (
              <HomeScreen
                vm={vm}
                loading={loading}
                error={error}
                alertFrom={alertFrom}
                onRetry={() => setReload((x) => x + 1)}
                onOpenAdvice={() => goTab('advice')}
              />
            ) : null}
            {tab === 'advice' ? (
              error && !vm ? <Banner kind="danger">{error}</Banner> : <AdviceScreen vm={vm} meta={meta} alertFrom={alertFrom} groupsLabel={groupsLabel} />
            ) : null}
            {tab === 'stations' ? (
              <StationsScreen data={stations.data} error={stations.error} current={profile.station} onPick={pickStation} mode={mode} />
            ) : null}
            {tab === 'week' ? <WeekScreen data={week.data} error={week.error} station={profile.station} /> : null}
            {tab === 'profile' ? (
              <ProfileScreen
                key={JSON.stringify(profile)}
                initial={profile}
                onSave={saveProfile}
                onTestServer={testServer}
                onTestNotification={testNotification}
              />
            ) : null}
          </View>
        )}
      </ScrollView>

      {toast ? (
        <View style={[styles.toast, { bottom: 80 + insets.bottom }]}>
          <Text style={{ color: '#fff', fontSize: 14 }}>{toast}</Text>
        </View>
      ) : null}

      {!welcome && tab === 'home' && mode === 'replay' && hours.length ? (
        <ReplayBar
          playing={playing}
          onPlay={onPlay}
          onStep={onStep}
          onSkip={onSkip}
          speed={speed}
          onSpeed={setSpeed}
          canBack={idx > 0}
          canForward={idx < hours.length - 1}
          skipMsg={skipMsg}
          clockText={'Replay · ' + (label ? fmtDay(labelFromMs(toMs(label) + HOUR)) + ', ' + fmtClock(labelFromMs(toMs(label) + HOUR)) : '')}
        />
      ) : null}

      {!welcome ? (
        <View style={[styles.tabbar, { paddingBottom: Math.max(insets.bottom, 10) + 6 }]}>
          {TABS.map((t) => {
            const on = tab === t.id;
            return (
              <TouchableOpacity
                key={t.id}
                testID={'tab_' + t.id}
                accessibilityRole="tab"
                accessibilityState={{ selected: on }}
                style={styles.tab}
                onPress={() => goTab(t.id)}
              >
                <Icon name={t.icon} size={22} color={on ? C.text : C.faint} width={on ? 2 : 1.8} />
                <Text style={[styles.tabLabel, on ? styles.tabOn : null]}>{t.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      ) : null}

      <AlertModal
        alert={alert}
        insets={insets}
        replay={mode === 'replay'}
        onDismiss={() => setAlert(null)}
        onContinue={() => {
          setAlert(null);
          setPlaying(true);
        }}
      />
    </View>
  );
}

// ---------------------------------------------------------------- helpers
function stepIndex(list, idx, hoursDelta) {
  if (idx < 0 || !list.length) return idx;
  const target = toMs(list[idx]) + hoursDelta * HOUR;
  if (hoursDelta > 0) {
    for (let j = idx + 1; j < list.length; j++) if (toMs(list[j]) >= target) return j;
    return list.length - 1;
  }
  for (let j = idx - 1; j >= 0; j--) if (toMs(list[j]) <= target) return j;
  return 0;
}

// "Skip to next pollution event": the first event whose lead hour (6 h before it) is after the current hour; land on the first
// replay hour at or after that lead hour and before the event (same rule as the website).
function pickJump(list, onsets, current) {
  for (const o of onsets) {
    const lead = labelFromMs(toMs(o.t) - 6 * HOUR);
    if (current != null && lead <= current) continue;
    const j = list.findIndex((x) => x >= lead && x < o.t);
    if (j >= 0) return j;
  }
  return null;
}

function fromReplay(s) {
  const nowMs = toMs(s.sim_time_end);
  const nowAqi = s.now && s.now.aqi != null ? Math.round(s.now.aqi) : null;
  return {
    mode: 'replay',
    stationName: s.station_name,
    banner: { tag: 'REPLAY', kind: 'replay', text: fmtTime(s.sim_time_end) + ' IST · simulated time' },
    timeLine: fmtDay(s.sim_time_end) + ' · ' + fmtClock(s.sim_time_end) + ' · replay',
    clock: s.sim_time_end,
    nowLabel: 'AQI for the hour ending ' + fmtTime(s.sim_time_end),
    now: nowAqi != null ? { aqi: nowAqi, category: catOf(nowAqi), dominant: s.now.dominant } : null,
    forecasts: (s.forecasts || []).filter((f) => f.horizon <= 24).map((f) => ({ ...f, past: false })),
    observed: (s.observed || [])
      .filter((o) => o.aqi != null)
      .map((o) => ({ offset: Math.round((toMs(o.t_end) - nowMs) / HOUR), aqi: Math.round(o.aqi), category: catOf(o.aqi) })),
    personal: s.personal,
    pollutants: s.pollutants,
    warnings: [],
    stale: false,
  };
}

function fromLive({ s, personal }) {
  const stale = s.severity === 'stale';
  const has = s.last_aqi != null;
  return {
    mode: 'live',
    stationName: s.station_name,
    banner: {
      tag: 'LIVE',
      kind: stale ? 'danger' : 'live',
      text: s.last_obs_end
        ? (stale ? 'DATA IS OLD · ' : '') + 'newest data ' + fmtTime(s.last_obs_end) + ' (' + Math.round(s.age_hours) + ' h old)'
        : 'No recent data for this station',
    },
    timeLine: s.last_obs_end
      ? (stale ? 'Last data ' : 'Updated ') + fmtDay(s.last_obs_end) + ' · ' + fmtClock(s.last_obs_end) + ' (' + Math.round(s.age_hours) + ' h ago)'
      : 'No recent data',
    clock: s.last_obs_end,
    nowLabel: has ? (stale ? 'Last known AQI, hour ending ' : 'AQI for the hour ending ') + fmtTime(s.last_obs_end) : '',
    now: has ? { aqi: s.last_aqi, category: catOf(s.last_aqi), dominant: s.dominant_now } : null,
    forecasts: (s.forecasts || []).filter((f) => f.horizon <= 24).map((f) => ({ ...f, available: true, past: f.status === 'past' })),
    observed: (s.observed || []).map((o) => ({ offset: Math.round(o.x), aqi: o.aqi, category: catOf(o.aqi) })),
    personal,
    pollutants: s.pollutants,
    warnings: s.warnings || [],
    stale,
  };
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 16, paddingBottom: 6, flexDirection: 'row', alignItems: 'center', backgroundColor: C.bg },
  appName: { color: C.text, fontSize: 20, fontWeight: '800', paddingVertical: 10, paddingLeft: 4 },
  stationBtn: { flexDirection: 'row', alignItems: 'center', minHeight: 44, paddingHorizontal: 4, maxWidth: 230 },
  stationText: { color: C.text, fontSize: 17, fontWeight: '600', marginHorizontal: 6 },
  modeChip: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, backgroundColor: C.card2, marginRight: 8 },
  modeChipText: { color: C.soft, fontWeight: '700', fontSize: 11, letterSpacing: 0.8 },
  gear: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  tabbar: { flexDirection: 'row', backgroundColor: C.nav, borderTopWidth: 1, borderTopColor: C.card2, paddingTop: 10 },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 2 },
  tabLabel: { fontSize: 11, color: C.faint, marginTop: 4, fontWeight: '500' },
  tabOn: { color: C.text, fontWeight: '700' },
  toast: { position: 'absolute', left: 24, right: 24, backgroundColor: C.card2, borderRadius: 12, padding: 12, alignItems: 'center' },
});
