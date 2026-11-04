// Building blocks shared by every screen: one place for the look (tokens come from theme.js).
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Switch } from 'react-native';
import Svg, { Path, Circle, Defs, RadialGradient, Stop } from 'react-native-svg';
import { C, F, R, SH, SH_SM, THEME, catStyle, pastel } from './theme';

// line icons (24 x 24, 1.75 px stroke, round caps)
const ICONS = {
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z',
  pin: 'M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
  calendar: 'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4',
  chevronDown: 'm6 9 6 6 6-6',
  chevronRight: 'm9 6 6 6-6 6',
  chevronLeft: 'm15 18-6-6 6-6',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  alert: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  down: 'm3 7 7 7 4-4 7 7M21 11v6h-6',
  up: 'm3 17 7-7 4 4 7-7M21 13V7h-6',
  steady: 'M4 12h16M15 7l5 5-5 5',
  medicine: 'm10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7zM8.5 8.5l7 7',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
  doctor: 'M5 3v6a5 5 0 0 0 10 0V3M10 14v2a5 5 0 0 0 10 0v-2M20 9a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
  walking: 'M13 4a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM9 20l3-6 3 3v4M6 12l4-4 4 3 3-1',
  mask: 'M4 9c3-2 13-2 16 0v3c0 4-4 7-8 7s-8-3-8-7zM4 10 2 9M20 10l2-1M8 13h8',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 8h.01',
  settings: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  check: 'm5 12 5 5 9-10',
  skip: 'M5 4v16l10-8zM19 5v14',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  phone: 'M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM11 18h2',
  speaker: 'M4 9h4l5-4v14l-5-4H4zM16.5 8.5a5 5 0 0 1 0 7M19.5 5.5a9 9 0 0 1 0 13',
  share: 'M12 3v12M7 8l5-5 5 5M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5',
  bell: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0',
  mail: 'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM3.5 6.5 12 13l8.5-6.5',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
  leaf: 'M5 19c0-8 5-14 15-14 0 10-6 15-14 15M5 19l7-7',
  server: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01',
};
const FILLED = {
  play: 'M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z',
  pause: 'M7 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM14 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z',
};

export function Icon({ name, size = 22, color = C.text, width = 1.75 }) {
  if (FILLED[name]) {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path d={FILLED[name]} fill={color} />
      </Svg>
    );
  }
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d={ICONS[name] || ICONS.info} stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </Svg>
  );
}

// ---------------------------------------------------------------- abstract 3D: a soft lit sphere in the category colour
let orbSeq = 0;
function shade(hex, amt) {
  const h = String(hex || '#999999').replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
  const f = (v) => Math.max(0, Math.min(255, Math.round(amt < 0 ? v * (1 + amt) : v + (255 - v) * amt)));
  const r = f((n >> 16) & 255), g = f((n >> 8) & 255), b = f(n & 255);
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
}
export function Orb({ color, size = 160, glow = true }) {
  const id = React.useMemo(() => 'orb' + ++orbSeq, []);
  const base = color || '#b9b0a4';
  return (
    <Svg width={size} height={size} viewBox="0 0 200 200">
      <Defs>
        <RadialGradient id={id + 'g'} cx="50%" cy="50%" r="50%">
          <Stop offset="55%" stopColor={base} stopOpacity={THEME === 'light' ? 0.32 : 0.4} />
          <Stop offset="100%" stopColor={base} stopOpacity={0} />
        </RadialGradient>
        <RadialGradient id={id + 's'} cx="36%" cy="30%" r="72%">
          <Stop offset="0%" stopColor={shade(base, 0.75)} stopOpacity={1} />
          <Stop offset="38%" stopColor={shade(base, 0.18)} stopOpacity={1} />
          <Stop offset="100%" stopColor={shade(base, -0.28)} stopOpacity={1} />
        </RadialGradient>
      </Defs>
      {glow ? <Circle cx={100} cy={100} r={100} fill={'url(#' + id + 'g)'} /> : null}
      <Circle cx={100} cy={100} r={64} fill={'url(#' + id + 's)'} />
    </Svg>
  );
}

// ambient glow behind a screen (decorative)
export function Glow({ width = 420, height = 420, a = C.glowA, b = C.glowB }) {
  const id = React.useMemo(() => 'glw' + ++orbSeq, []);
  return (
    <Svg width={width} height={height} viewBox="0 0 420 420">
      <Defs>
        <RadialGradient id={id + 'a'} cx="50%" cy="50%" r="50%">
          <Stop offset="0%" stopColor={a} stopOpacity={1} />
          <Stop offset="100%" stopColor={a} stopOpacity={0} />
        </RadialGradient>
        <RadialGradient id={id + 'b'} cx="50%" cy="50%" r="50%">
          <Stop offset="0%" stopColor={b} stopOpacity={1} />
          <Stop offset="100%" stopColor={b} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx={300} cy={110} r={150} fill={'url(#' + id + 'a)'} />
      <Circle cx={120} cy={250} r={170} fill={'url(#' + id + 'b)'} />
    </Svg>
  );
}

// ---------------------------------------------------------------- layout and text
export function Card({ children, style, tone }) {
  const t = tone != null ? pastel(tone) : null;
  return <View style={[s.card, t ? { backgroundColor: t.bg, shadowOpacity: 0, elevation: 0 } : null, style]}>{children}</View>;
}

export function H2({ children, right }) {
  return (
    <View style={s.h2row}>
      <Text style={s.h2}>{children}</Text>
      {right || null}
    </View>
  );
}

export function Overline({ children, style, color }) {
  return <Text style={[s.overline, color ? { color } : null, style]}>{children}</Text>;
}

export function Title({ children, style }) {
  return <Text style={[s.title, style]}>{children}</Text>;
}

export function Muted({ children, style }) {
  return <Text style={[s.muted, style]}>{children}</Text>;
}

export function Dot({ category, size = 10 }) {
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: catStyle(category).bg }} />;
}

export function CatText({ category, size = 15 }) {
  if (!category) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
      <Dot category={category} size={Math.round(size * 0.6)} />
      <Text style={{ marginLeft: 6, color: C.text, fontSize: size, fontWeight: '600' }}>{category}</Text>
    </View>
  );
}

export function CatPill({ category, label, small }) {
  const c = catStyle(category);
  return (
    <View style={[s.catPill, { backgroundColor: c.bg }, small ? { paddingVertical: 3, paddingHorizontal: 10 } : null]}>
      <Text style={{ color: c.fg, fontWeight: '700', fontSize: small ? 12 : 14 }}>{label || category}</Text>
    </View>
  );
}

// ---------------------------------------------------------------- controls
export function Btn({ title, onPress, kind = 'primary', small, disabled, style, testID, icon }) {
  const box = kind === 'primary' ? s.btnPrimary : kind === 'ghost' ? s.btnGhost : kind === 'tonal' ? s.btnTonal : s.btnSecondary;
  const tx = kind === 'primary' ? s.btnTextPrimary : kind === 'tonal' ? s.btnTextTonal : s.btnTextOther;
  const ic = kind === 'primary' ? C.onPrimary : kind === 'tonal' ? C.peachText : C.accent;
  return (
    <TouchableOpacity
      testID={testID}
      accessibilityRole="button"
      activeOpacity={0.78}
      disabled={disabled}
      onPress={onPress}
      style={[s.btn, box, small ? s.btnSmall : null, disabled ? { opacity: 0.45 } : null, style]}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        {icon ? <View style={{ marginRight: 8 }}><Icon name={icon} size={small ? 17 : 19} color={ic} /></View> : null}
        <Text style={[tx, small ? { fontSize: 14 } : null]}>{title}</Text>
      </View>
    </TouchableOpacity>
  );
}

export function IconBtn({ icon, label, onPress, testID, active, style }) {
  return (
    <TouchableOpacity
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      activeOpacity={0.75}
      onPress={onPress}
      style={[s.iconBtn, active ? { backgroundColor: C.primary } : null, style]}
    >
      <Icon name={icon} size={20} color={active ? C.onPrimary : C.text} />
    </TouchableOpacity>
  );
}

export function Chip({ label, active, onPress }) {
  return (
    <TouchableOpacity
      accessibilityRole="button"
      accessibilityState={{ selected: !!active }}
      activeOpacity={0.75}
      onPress={onPress}
      style={[s.chip, active ? s.chipOn : null]}
    >
      {active ? <View style={{ marginRight: 6 }}><Icon name="check" size={14} color={C.onPrimary} width={2.4} /></View> : null}
      <Text style={[s.chipText, active ? s.chipTextOn : null]}>{label}</Text>
    </TouchableOpacity>
  );
}

// one-of-N choice (theme, mode, alert level)
export function Segmented({ options, value, onChange, testID }) {
  return (
    <View style={s.seg} testID={testID} accessibilityRole="radiogroup">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <TouchableOpacity
            key={String(o.value)}
            testID={o.testID}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            activeOpacity={0.8}
            onPress={() => onChange(o.value)}
            style={[s.segItem, on ? s.segOn : null]}
          >
            {o.icon ? <View style={{ marginRight: 6 }}><Icon name={o.icon} size={16} color={on ? C.text : C.muted} /></View> : null}
            <Text style={[s.segText, on ? s.segTextOn : null]}>{o.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export function Toggle({ value, onValueChange, label }) {
  return (
    <Switch
      value={!!value}
      onValueChange={onValueChange}
      accessibilityLabel={label}
      trackColor={{ true: C.primary, false: C.line }}
      thumbColor={value ? C.onPrimary : C.card}
      ios_backgroundColor={C.line}
    />
  );
}

// renders **bold** markers from the backend's "marked" text
export function Rich({ text, style }) {
  const parts = String(text || '').split('**');
  return (
    <Text style={style}>
      {parts.map((p, i) => (i % 2 === 1 ? <Text key={i} style={{ fontWeight: '700', color: C.text }}>{p}</Text> : p))}
    </Text>
  );
}

export function Banner({ kind = 'info', children, icon }) {
  const bg = kind === 'danger' ? C.dangerBg : kind === 'warn' ? C.warnBg : C.infoBg;
  const fg = kind === 'danger' ? C.dangerText : kind === 'warn' ? C.warnText : C.infoText;
  const ic = icon || (kind === 'info' ? 'info' : 'alert');
  return (
    <View style={[s.banner, { backgroundColor: bg }]}>
      <View style={{ marginRight: 10, marginTop: 1 }}><Icon name={ic} size={18} color={fg} /></View>
      <Text style={{ color: fg, fontSize: 14, lineHeight: 20, flex: 1 }}>{children}</Text>
    </View>
  );
}

export function Loading({ text }) {
  return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator color={C.accent} size="large" />
      {text ? <Text style={[s.muted, { marginTop: 14 }]}>{text}</Text> : null}
    </View>
  );
}

// short, plain title for an advice line, by its icon; the full sourced wording is shown under it
const TITLE = {
  walking: 'Limit outdoor activity',
  medicine: 'Keep medicines close',
  clock: 'Best time to go out',
  doctor: 'When to see a doctor',
  home: 'Stay indoors',
  mask: 'About masks',
  info: 'Good to know',
};
export const titleFor = (icon) => TITLE[icon] || TITLE.info;

export function ActionCard({ icon, marked, text, source, title, index = 0 }) {
  const t = pastel(index);
  return (
    <View style={s.action}>
      <View style={[s.actionIcon, { backgroundColor: t.bg }]}>
        <Icon name={icon || 'info'} size={22} color={t.fg} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.actionTitle}>{title || titleFor(icon)}</Text>
        <Rich text={marked || text} style={s.actionText} />
        {source ? <Text style={s.src}>{source}</Text> : null}
      </View>
    </View>
  );
}

export const s = StyleSheet.create({
  card: { backgroundColor: C.card, borderRadius: R.lg, padding: 18, marginBottom: 12, ...SH_SM },
  h2row: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 },
  h2: { fontFamily: F.serif, fontSize: 21, fontWeight: '600', color: C.text, letterSpacing: -0.2 },
  title: { fontFamily: F.serif, fontSize: 34, lineHeight: 40, fontWeight: '600', color: C.text, letterSpacing: -0.6 },
  overline: { color: C.muted, fontSize: 11, fontWeight: '700', letterSpacing: 1.4, textTransform: 'uppercase' },
  muted: { color: C.muted, fontSize: 14, lineHeight: 20 },
  body: { color: C.soft, fontSize: 15, lineHeight: 23 },
  src: { color: C.faint, fontSize: 12, marginTop: 4 },
  catPill: { alignSelf: 'flex-start', borderRadius: R.pill, paddingHorizontal: 14, paddingVertical: 6 },
  btn: { borderRadius: R.pill, height: 54, paddingHorizontal: 22, alignItems: 'center', justifyContent: 'center' },
  btnSmall: { height: 46, paddingHorizontal: 18 },
  btnPrimary: { backgroundColor: C.primary },
  btnSecondary: { backgroundColor: C.card, ...SH_SM },
  btnTonal: { backgroundColor: C.peach },
  btnGhost: { backgroundColor: 'transparent' },
  btnTextPrimary: { color: C.onPrimary, fontWeight: '600', fontSize: 16 },
  btnTextTonal: { color: C.peachText, fontWeight: '600', fontSize: 15 },
  btnTextOther: { color: C.text, fontWeight: '600', fontSize: 15 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card, ...SH_SM },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
    minHeight: 40,
    borderRadius: R.pill,
    backgroundColor: C.card2,
    marginRight: 8,
    marginBottom: 8,
  },
  chipOn: { backgroundColor: C.primary },
  chipText: { color: C.soft, fontSize: 14, fontWeight: '500' },
  chipTextOn: { color: C.onPrimary, fontWeight: '600' },
  seg: { flexDirection: 'row', backgroundColor: C.card2, borderRadius: R.pill, padding: 4 },
  segItem: { flex: 1, flexDirection: 'row', minHeight: 42, borderRadius: R.pill, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  segOn: { backgroundColor: C.card, ...SH_SM },
  segText: { color: C.muted, fontSize: 14, fontWeight: '500' },
  segTextOn: { color: C.text, fontWeight: '600' },
  banner: { flexDirection: 'row', alignItems: 'flex-start', borderRadius: R.md, padding: 14, marginBottom: 12 },
  action: { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: C.card, borderRadius: R.lg, padding: 16, marginBottom: 10, ...SH_SM },
  actionIcon: { width: 46, height: 46, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  actionTitle: { color: C.text, fontSize: 16, fontWeight: '600', marginBottom: 4 },
  actionText: { color: C.muted, fontSize: 14, lineHeight: 21 },
});
export { SH, SH_SM };
