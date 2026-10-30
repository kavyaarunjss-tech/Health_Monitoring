// Small building blocks used by the screens.
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { C, catStyle } from './theme';

export function Card({ children, style, accent }) {
  return <View style={[s.card, accent ? { borderLeftWidth: 6, borderLeftColor: accent } : null, style]}>{children}</View>;
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

export function Pill({ category, small }) {
  if (!category) return null;
  const c = catStyle(category);
  return (
    <View style={[s.pill, small ? s.pillSmall : null, { backgroundColor: c.bg }]}>
      <Text style={[s.pillText, small ? { fontSize: 11 } : null, { color: c.fg }]} numberOfLines={1}>
        {category}
      </Text>
    </View>
  );
}

export function Btn({ title, onPress, kind = 'primary', small, disabled, style, testID }) {
  const st = kind === 'primary' ? s.btnPrimary : kind === 'danger' ? s.btnDanger : s.btnSecondary;
  const tx = kind === 'secondary' ? s.btnTextSecondary : s.btnText;
  return (
    <TouchableOpacity
      testID={testID}
      accessibilityRole="button"
      activeOpacity={0.75}
      disabled={disabled}
      onPress={onPress}
      style={[s.btn, st, small ? s.btnSmall : null, disabled ? { opacity: 0.45 } : null, style]}
    >
      <Text style={[tx, small ? { fontSize: 13 } : null]}>{title}</Text>
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
      <Text style={[s.chipText, active ? s.chipTextOn : null]}>{active ? '✓ ' : ''}{label}</Text>
    </TouchableOpacity>
  );
}

// renders **bold** markers from the backend's "marked" text
export function Rich({ text, style }) {
  const parts = String(text || '').split('**');
  return (
    <Text style={style}>
      {parts.map((p, i) => (i % 2 === 1 ? <Text key={i} style={{ fontWeight: '700' }}>{p}</Text> : p))}
    </Text>
  );
}

export function Banner({ kind = 'info', children }) {
  const bg = kind === 'danger' ? '#fdecec' : kind === 'warn' ? C.warnBg : C.infoBg;
  const fg = kind === 'danger' ? '#8e1b1b' : kind === 'warn' ? C.warnText : C.navy;
  return (
    <View style={[s.banner, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 14, lineHeight: 20 }}>{children}</Text>
    </View>
  );
}

export function Loading({ text }) {
  return (
    <View style={{ padding: 32, alignItems: 'center' }}>
      <ActivityIndicator color={C.teal} size="large" />
      {text ? <Text style={[s.muted, { marginTop: 12 }]}>{text}</Text> : null}
    </View>
  );
}

const ICON = { walking: '🚶', clock: '⏰', doctor: '🩺', medicine: '💊', home: '🏠', mask: '😷', info: 'ℹ️' };
export const iconFor = (name) => ICON[name] || '•';

export function ActionRow({ icon, marked, text, source }) {
  return (
    <View style={s.action}>
      <Text style={s.actionIcon}>{iconFor(icon)}</Text>
      <View style={{ flex: 1 }}>
        <Rich text={marked || text} style={s.body} />
        {source ? <Text style={s.src}>{source}</Text> : null}
      </View>
    </View>
  );
}

export const s = StyleSheet.create({
  card: {
    backgroundColor: C.card,
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: C.border,
  },
  h2row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  h2: { fontSize: 17, fontWeight: '700', color: C.text },
  muted: { color: C.muted, fontSize: 13, lineHeight: 18 },
  body: { color: C.text, fontSize: 15, lineHeight: 21 },
  src: { color: C.muted, fontSize: 12, marginTop: 2 },
  pill: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 999, alignSelf: 'flex-start' },
  pillSmall: { paddingHorizontal: 8, paddingVertical: 2 },
  pillText: { fontWeight: '700', fontSize: 13 },
  btn: { borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' },
  btnSmall: { paddingVertical: 8, paddingHorizontal: 12 },
  btnPrimary: { backgroundColor: C.teal },
  btnDanger: { backgroundColor: C.danger },
  btnSecondary: { backgroundColor: '#ffffff', borderWidth: 1, borderColor: C.teal },
  btnText: { color: '#ffffff', fontWeight: '700', fontSize: 15 },
  btnTextSecondary: { color: C.teal, fontWeight: '700', fontSize: 15 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: C.border,
    backgroundColor: '#ffffff',
    marginRight: 8,
    marginBottom: 8,
  },
  chipOn: { backgroundColor: C.teal, borderColor: C.teal },
  chipText: { color: C.text, fontSize: 14 },
  chipTextOn: { color: '#ffffff', fontWeight: '700' },
  banner: { borderRadius: 10, padding: 12, marginBottom: 12 },
  action: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.border },
  actionIcon: { fontSize: 20, width: 32 },
});
