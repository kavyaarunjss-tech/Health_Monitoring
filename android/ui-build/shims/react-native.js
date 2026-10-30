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
const VIEW = { display: 'flex', flexDirection: 'column', position: 'relative', boxSizing: 'border-box', flexShrink: 0, minWidth: 0 };

export const View = forwardRef(function View({ style, children, testID }, ref) {
  return <div ref={ref} data-testid={testID} style={css(style, VIEW)}>{children}</div>;
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

export function TouchableOpacity({ style, children, onPress, disabled, testID, accessibilityRole }) {
  return (
    <div
      role={accessibilityRole || 'button'}
      data-testid={testID}
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

export function TextInput({ value, onChangeText, placeholder, style }) {
  return <input value={value || ''} placeholder={placeholder} onChange={(e) => onChangeText && onChangeText(e.target.value)} style={css(style, { boxSizing: 'border-box', width: '100%' })} />;
}
export function Switch({ value, onValueChange }) {
  return <input type="checkbox" checked={!!value} onChange={(e) => onValueChange && onValueChange(e.target.checked)} style={{ width: 40, height: 22 }} />;
}
export function Modal({ visible, children }) {
  if (!visible) return null;
  return <div data-modal="1" style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', flexDirection: 'column' }}>{children}</div>;
}
export function ActivityIndicator() {
  return <div style={{ fontSize: 24 }}>…</div>;
}
export function RefreshControl() {
  return null;
}
export const StyleSheet = { create: (x) => x, flatten: flat };
export const Platform = { OS: 'android', select: (o) => o.android ?? o.default };
export const LogBox = { ignoreLogs() {} };
export const Linking = { openURL: (u) => (window.__aqOpen ? window.__aqOpen(u) : console.log('openURL', u)) };
export const StatusBar = { currentHeight: 24 };
export default { View, Text };
