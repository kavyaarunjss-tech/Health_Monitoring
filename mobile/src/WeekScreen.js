// Your week: one headline, 7 coloured days, two numbers, one tip; the full weekly advice behind "Show details".
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { C, F, R, SH_SM, catStyle, catRank, pname, stationShort } from './theme';
import { Card, Muted, Loading, Banner, ActionCard, Rich, Icon, Overline, s as ui } from './ui';

export default function WeekScreen({ data, error, station }) {
  const [open, setOpen] = useState(false);
  if (error) return <Banner kind="danger">{error}</Banner>;
  if (!data) return <Loading text="Loading the week..." />;
  const stale = data.data && data.data.stale;
  const days = data.days || [];
  const valid = days.filter((d) => d.valid);
  const bad = valid.filter((d) => catRank(d.category) >= 2).length;
  const counts = {};
  valid.forEach((d) => (counts[d.category] = (counts[d.category] || 0) + 1));
  const most = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
  const tr = data.trend || {};
  const trend =
    tr.direction === 'rising' ? { t: 'Worse', icon: 'up', color: C.warnIcon } :
    tr.direction === 'falling' ? { t: 'Better', icon: 'down', color: C.good } :
    tr.direction === 'steady' ? { t: 'Steady', icon: 'steady', color: C.soft } : null;
  const h = data.health || {};
  const top = (data.top3 || []).map((id) => (h.actions || []).find((a) => a.id === id)).filter(Boolean);
  const used = new Set((data.top3 || []).slice(0, 1));
  const topAqi = Math.max(150, ...days.map((d) => (d.valid ? d.aqi : 0)));
  const rest = (h.actions || []).filter((a) => !used.has(a.id));
  return (
    <View>
      <Overline style={{ marginTop: 8 }}>{(stale ? 'Last available week' : 'Your week') + ' · ' + stationShort(station)}</Overline>
      <Text style={st.h1}>{data.enough && most ? 'Mostly ' + most + ' air ' + (stale ? 'that week' : 'this week') : 'Not enough data this week'}</Text>
      {stale ? <Banner kind="danger">Data feed stopped: this is the newest week with data, not the current week.</Banner> : null}

      {!data.enough ? (
        <Card>
          <Muted>A weekly summary needs at least 5 of 7 days with valid data.</Muted>
        </Card>
      ) : (
        <View>
          <Card style={{ paddingTop: 20, paddingBottom: 16 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', height: 132 }}>
              {days.map((d, i) => (
                <View key={d.date} style={{ alignItems: 'center', flex: 1 }}>
                  <Text style={st.dayAqi}>{d.valid ? d.aqi : '–'}</Text>
                  <View style={[st.day, { height: d.valid ? Math.max(18, (d.aqi / topAqi) * 96) : 18, backgroundColor: d.valid ? catStyle(d.category).bg : C.card2 }]} />
                  <Text style={[st.wd, i === days.length - 1 ? { color: C.text, fontWeight: '700' } : null]}>{d.weekday}</Text>
                </View>
              ))}
            </View>
            <View style={st.legend}>
              {Object.keys(counts).map((c) => (
                <View key={c} style={{ flexDirection: 'row', alignItems: 'center', marginHorizontal: 7, marginTop: 4 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: catStyle(c).bg, marginRight: 6 }} />
                  <Text style={{ color: C.muted, fontSize: 12 }}>{c}</Text>
                </View>
              ))}
            </View>
          </Card>

          <View style={{ flexDirection: 'row' }}>
            <Card tone={1} style={{ flex: 1, marginRight: 6 }}>
              <Text style={st.stat}>{bad}<Text style={st.statOf}>{' of 7'}</Text></Text>
              <Text style={st.statLbl}>days Moderate or worse</Text>
            </Card>
            <Card tone={0} style={{ flex: 1, marginLeft: 6 }}>
              {trend ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 6 }}>
                  <Icon name={trend.icon} size={22} color={C.peachText} width={2} />
                  <Text style={st.trend}>{trend.t}</Text>
                </View>
              ) : (
                <Text style={st.trend}>–</Text>
              )}
              <Text style={st.statLbl}>than the days before</Text>
            </Card>
          </View>

          {top[0] ? <ActionCard icon={top[0].icon} marked={top[0].marked} text={top[0].text} source={'[' + top[0].sources.join('][') + ']'} title="This week's tip" /> : null}

          <TouchableOpacity onPress={() => setOpen(!open)} accessibilityRole="button" style={st.more}>
            <Text style={{ color: C.text, fontWeight: '600', fontSize: 15, marginRight: 6 }}>{open ? 'Hide details' : 'Show details'}</Text>
            <Icon name={open ? 'chevronDown' : 'chevronRight'} size={16} color={C.text} />
          </TouchableOpacity>

          {open ? (
            <View>
              {days.length ? (
                <Card>
                  <Text style={[ui.h2, { marginBottom: 6 }]}>Daily AQI</Text>
                  {days.map((d) => (
                    <View key={d.date} style={st.dayRow}>
                      <Text style={{ color: C.soft, width: 90 }}>{d.weekday + ' ' + d.label}</Text>
                      <Text style={{ color: C.text, fontWeight: '700', width: 44 }}>{d.valid ? d.aqi : '–'}</Text>
                      <Text style={{ color: C.muted, flex: 1 }}>{d.valid ? d.category + (d.dominant ? ' · ' + pname(d.dominant) : '') : 'not enough hours'}</Text>
                    </View>
                  ))}
                </Card>
              ) : null}
              <Section title={stale ? 'Air like that week may have affected you' : 'Air like this may affect you'} items={h.short_term} />
              <Section title="If this continues" items={h.long_term} />
              <Section title="Good news" items={h.clean} />
              {rest.length ? (
                <Card>
                  <Text style={[ui.h2, { marginBottom: 6 }]}>Things you can do</Text>
                  {rest.map((a) => (
                    <View key={a.id} style={{ paddingVertical: 6 }}>
                      <Rich text={'• ' + (a.marked || a.text)} style={ui.body} />
                      <Text style={ui.src}>{'[' + a.sources.join('][') + ']'}</Text>
                    </View>
                  ))}
                </Card>
              ) : null}
            </View>
          ) : null}
        </View>
      )}
      <Text style={st.foot}>{data.disclaimer}</Text>
    </View>
  );
}

function Section({ title, items }) {
  if (!items || !items.length) return null;
  return (
    <Card>
      <Text style={[ui.h2, { marginBottom: 6 }]}>{title}</Text>
      {items.map((x) => (
        <View key={x.id} style={{ paddingVertical: 6 }}>
          <Rich text={'• ' + (x.marked || x.text)} style={ui.body} />
          <Text style={ui.src}>{'[' + (x.sources || []).join('][') + ']'}</Text>
        </View>
      ))}
    </Card>
  );
}

const st = StyleSheet.create({
  h1: { fontFamily: F.serif, color: C.text, fontSize: 34, fontWeight: '600', letterSpacing: -0.6, lineHeight: 41, marginTop: 6, marginBottom: 20 },
  day: { width: 28, borderRadius: 14 },
  dayAqi: { color: C.soft, fontSize: 11, fontWeight: '600', marginBottom: 6 },
  wd: { color: C.muted, fontSize: 12, fontWeight: '500', marginTop: 10 },
  legend: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', marginTop: 16 },
  stat: { fontFamily: F.serif, color: C.sageText, fontSize: 40, fontWeight: '600', letterSpacing: -1 },
  statOf: { fontFamily: F.serif, color: C.sageText, fontSize: 18, fontWeight: '500' },
  statLbl: { color: C.soft, fontSize: 13, marginTop: 4 },
  trend: { fontFamily: F.serif, color: C.peachText, fontSize: 28, fontWeight: '600', marginLeft: 6 },
  more: { height: 52, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: R.pill, backgroundColor: C.card2, marginVertical: 6 },
  dayRow: { flexDirection: 'row', paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.line },
  foot: { color: C.faint, fontSize: 12, textAlign: 'center', marginVertical: 12 },
});
