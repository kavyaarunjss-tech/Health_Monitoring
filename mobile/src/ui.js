// Building blocks shared by the screens (dark theme, line icons).
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { C, catStyle } from './theme';

// line icons (24 x 24, stroke)
const ICONS = {
  home: 'M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z',
  heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z',
  pin: 'M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
  calendar: 'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4',
  chevronDown: 'm6 9 6 6 6-6',
  chevronRight: 'm9 6 6 6-6 6',
  chevronLeft: 'm15 18-6-6 6-6',
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
  bell: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0',
};
const FILLED = {
  play: 'M7 4v16l13-8z',
  pause: 'M6 4h4v16H6zM14 4h4v16h-4z',
};

export function Icon({ name, size = 22, color = C.text, width = 2 }) {
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

export function Card({ children, style }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function H2({ children, right }) {
  return (
    <View style={s.h2row}>
      <Text style={s.h2}>{children}</Text>
      {right || null}
    </View>
  );
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

export function Btn({ title, onPress, kind = 'primary', small, disabled, style, testID, icon }) {
  const box = kind === 'primary' ? s.btnPrimary : kind === 'ghost' ? s.btnGhost : s.btnSecondary;
  const tx = kind === 'primary' ? s.btnTextPrimary : s.btnTextOther;
  return (
    <TouchableOpacity
      testID={testID}
      accessibilityRole="button"
      activeOpacity={0.75}
      disabled={disabled}
      onPress={onPress}
      style={[s.btn, box, small ? s.btnSmall : null, disabled ? { opacity: 0.45 } : null, style]}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Text style={[tx, small ? { fontSize: 14 } : null]}>{title}</Text>
        {icon ? <View style={{ marginLeft: 8 }}><Icon name={icon} size={18} color={kind === 'primary' ? C.bg : C.accent} /></View> : null}
      </View>
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
      <Text style={[s.chipText, active ? s.chipTextOn : null]}>{label}</Text>
    </TouchableOpacity>
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

export function Banner({ kind = 'info', children }) {
  const bg = kind === 'danger' ? C.dangerBg : kind === 'warn' ? C.warnBg : C.infoBg;
  const fg = kind === 'danger' ? C.dangerText : kind === 'warn' ? C.warnText : C.infoText;
  return (
    <View style={[s.banner, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 14, lineHeight: 20 }}>{children}</Text>
    </View>
  );
}

export function Loading({ text }) {
  return (
    <View style={{ padding: 32, alignItems: 'center' }}>
      <ActivityIndicator color={C.accent} size="large" />
      {text ? <Text style={[s.muted, { marginTop: 12 }]}>{text}</Text> : null}
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

export function ActionCard({ icon, marked, text, source, title }) {
  return (
    <View style={s.action}>
      <View style={s.actionIcon}>
        <Icon name={icon || 'info'} size={24} />
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
  card: { backgroundColor: C.card, borderRadius: 20, padding: 16, marginBottom: 12 },
  h2row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  h2: { fontSize: 17, fontWeight: '700', color: C.text },
  muted: { color: C.muted, fontSize: 14, lineHeight: 20 },
  body: { color: C.soft, fontSize: 15, lineHeight: 22 },
  src: { color: C.faint, fontSize: 12, marginTop: 3 },
  btn: { borderRadius: 16, height: 54, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center' },
  btnSmall: { height: 44, borderRadius: 12 },
  btnPrimary: { backgroundColor: C.text },
  btnSecondary: { backgroundColor: C.card2 },
  btnGhost: { backgroundColor: 'transparent' },
  btnTextPrimary: { color: C.bg, fontWeight: '700', fontSize: 16 },
  btnTextOther: { color: C.accent, fontWeight: '700', fontSize: 15 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'transparent',
    backgroundColor: C.card,
    marginRight: 8,
    marginBottom: 8,
  },
  chipOn: { backgroundColor: C.selBg, borderColor: C.selBorder },
  chipText: { color: C.soft, fontSize: 14, fontWeight: '500' },
  chipTextOn: { color: C.text, fontWeight: '700' },
  banner: { borderRadius: 16, padding: 14, marginBottom: 12 },
  action: { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: C.card, borderRadius: 18, padding: 16, marginBottom: 10 },
  actionIcon: { width: 48, height: 48, borderRadius: 14, backgroundColor: C.card2, alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  actionTitle: { color: C.text, fontSize: 17, fontWeight: '700', marginBottom: 3 },
  actionText: { color: C.muted, fontSize: 14, lineHeight: 20 },
});
