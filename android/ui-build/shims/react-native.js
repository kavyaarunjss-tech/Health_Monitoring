// Test-only: a small React Native -> react-dom shim so the app's real code can be rendered in headless Chrome.
import React, { createContext, useContext, forwardRef, useImperativeHandle, useRef } from 'react';

const InText = createContext(false);

function flat(style) {
  if (!style) return {};
  if (Array.isArray(style)) return Object.assign({}, ...style.map(flat));
  if (typeof style === 'function') return {};
  return style;
}
const PX = new Set(['lineHeight']);
function css(style, base = {}) {
  const s = { ...base, ...flat(style) };
  const o = {};
  let border = Object.keys(s).some((k) => /^border.*Width$/.test(k));
  if (border) { o.borderStyle = 'solid'; o.borderWidth = s.borderWidth || 0; o.borderColor = s.borderColor || 'black'; }
  for (const [k, v] of Object.entries(s)) {
    if (v === undefined || v === null) continue;
    if (k === 'shadowColor') { o.boxShadow = shadowCss(s); continue; }
    if (k.startsWith('shadow') || k === 'elevation') continue;
    if (k === 'paddingHorizontal') { o.paddingLeft = v; o.paddingRight = v; continue; }
    if (k === 'paddingVertical') { o.paddingTop = v; o.paddingBottom = v; continue; }
    if (k === 'marginHorizontal') { o.marginLeft = v; o.marginRight = v; continue; }
    if (k === 'marginVertical') { o.marginTop = v; o.marginBottom = v; continue; }
    if (k === 'flex' && typeof v === 'number') { o.flex = v > 0 ? `${v} 1 0%` : 'none'; continue; }
    if (k === 'borderWidth' || k === 'borderColor') continue;
    o[k] = PX.has(k) && typeof v === 'number' ? v + 'px' : v;
  }
  return o;
}
function hexA(hex, a) {
  const h = String(hex || '#000').replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
function shadowCss(s) {
  const op = s.shadowOpacity == null ? 0 : s.shadowOpacity;
  if (!op) return 'none';
  const off = s.shadowOffset || { width: 0, height: 0 };
  return `${off.width || 0}px ${off.height || 0}px ${s.shadowRadius || 0}px ${hexA(s.shadowColor, op)}`;
}
const VIEW = { display: 'flex', flexDirection: 'column', position: 'relative', boxSizing: 'border-box', flexShrink: 0, minWidth: 0 };

export const View = forwardRef(function View({ style, children, testID, pointerEvents, accessibilityRole, accessibilityLabel }, ref) {
  const pe = pointerEvents === 'none' ? { pointerEvents: 'none' } : null;
  return <div ref={ref} data-testid={testID} role={accessibilityRole} aria-label={accessibilityLabel} aria-hidden={pointerEvents === 'none' ? 'true' : undefined} style={{ ...css(style, VIEW), ...pe }}>{children}</div>;
});

export function Text({ style, children, numberOfLines, testID }) {
  const inside = useContext(InText);
  const base = inside ? {} : { display: 'block', whiteSpace: 'pre-wrap', fontSize: 14, color: '#000', boxSizing: 'border-box', flexShrink: 0 };
  const extra = numberOfLines ? { display: '-webkit-box', WebkitLineClamp: numberOfLines, WebkitBoxOrient: 'vertical', overflow: 'hidden' } : {};
  const Tag = inside ? 'span' : 'div';
  return (
    <InText.Provider value={true}>
      <Tag data-testid={testID} style={{ ...css(style, base), ...extra }}>{children}</Tag>
    </InText.Provider>
  );
}

export function TouchableOpacity({ style, children, onPress, disabled, testID, accessibilityRole, accessibilityLabel, accessibilityState }) {
  const st = accessibilityState || {};
  const role = accessibilityRole || 'button';
  return (
    <div
      role={role}
      data-testid={testID}
      tabIndex={disabled ? -1 : 0}
      aria-label={accessibilityLabel}
      aria-selected={role === 'tab' && st.selected != null ? String(!!st.selected) : undefined}
      aria-checked={role === 'radio' && st.selected != null ? String(!!st.selected) : undefined}
      aria-pressed={role === 'button' && st.selected != null ? String(!!st.selected) : undefined}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !disabled && onPress) { e.preventDefault(); onPress(); } }}
      aria-disabled={disabled ? 'true' : undefined}
      onClick={() => !disabled && onPress && onPress()}
      style={css(style, { ...VIEW, cursor: 'pointer' })}
    >
      {children}
    </div>
  );
}
export const Pressable = TouchableOpacity;

export const ScrollView = forwardRef(function ScrollView({ style, contentContainerStyle, children }, ref) {
  const el = useRef(null);
  useImperativeHandle(ref, () => ({ scrollTo: ({ y }) => el.current && (el.current.scrollTop = y || 0) }));
  return (
    <div ref={el} data-scroll="1" style={css(style, { ...VIEW, overflowY: 'auto', flexShrink: 1 })}>
      <div style={css(contentContainerStyle, VIEW)}>{children}</div>
    </div>
  );
});

export function TextInput({ value, onChangeText, placeholder, style, secureTextEntry, keyboardType, autoCapitalize }) {
  const type = secureTextEntry ? 'password' : keyboardType === 'email-address' ? 'email' : keyboardType === 'url' ? 'url' : 'text';
  return <input type={type} autoCapitalize={autoCapitalize === 'none' ? 'off' : undefined} spellCheck={false} value={value || ''} placeholder={placeholder} onChange={(e) => onChangeText && onChangeText(e.target.value)} style={css(style, { boxSizing: 'border-box', width: '100%' })} />;
}
export function Switch({ value, onValueChange, trackColor, thumbColor, accessibilityLabel }) {
  const on = !!value;
  const track = (trackColor && (on ? trackColor.true : trackColor.false)) || (on ? '#333' : '#ccc');
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on ? 'true' : 'false'}
      aria-label={accessibilityLabel}
      onClick={() => onValueChange && onValueChange(!on)}
      style={{ width: 52, height: 32, borderRadius: 16, border: 0, padding: 0, background: track, position: 'relative', cursor: 'pointer', flexShrink: 0, transition: 'background .2s' }}
    >
      <span style={{ position: 'absolute', top: 4, left: on ? 24 : 4, width: 24, height: 24, borderRadius: 12, background: thumbColor || '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.25)', transition: 'left .2s' }} />
    </button>
  );
}
export function Modal({ visible, children }) {
  if (!visible) return null;
  return <div data-modal="1" style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', flexDirection: 'column' }}>{children}</div>;
}
export function ActivityIndicator({ color }) {
  return <div role="progressbar" aria-label="Loading" style={{ width: 34, height: 34, borderRadius: 17, border: '3px solid ' + hexA(color || '#888888', 0.22), borderTopColor: color || '#888', animation: 'aqspin .9s linear infinite' }} />;
}
export function RefreshControl() {
  return null;
}
export const StyleSheet = { create: (x) => x, flatten: flat };
export const Appearance = {
  getColorScheme: () => (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  addChangeListener: () => ({ remove() {} }),
};
export const Platform = { OS: 'android', select: (o) => o.android ?? o.default };
export const LogBox = { ignoreLogs() {} };
export const Linking = { openURL: (u) => (window.__aqOpen ? window.__aqOpen(u) : console.log('openURL', u)) };
export const StatusBar = { currentHeight: 24 };
export default { View, Text };
