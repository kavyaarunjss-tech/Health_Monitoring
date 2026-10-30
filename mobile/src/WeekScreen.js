// "This week's air and your health": the 7 complete days before the replay time (or the newest live data).
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { C, catStyle, catRank, pname } from './theme';
import { Card, H2, Muted, Loading, Banner, ActionRow, Rich, s } from './ui';

export default function WeekScreen({ data, error }) {
  if (error) return <Banner kind="danger">{error}</Banner>;
  if (!data) return <Loading text="Loading the week..." />;
  const stale = data.data && data.data.stale;
  const days = data.days || [];
  const bad = days.filter((d) => d.valid && catRank(d.category) >= 2).length;
  const max = Math.max(150, ...days.map((d) => d.aqi || 0)) * 1.1;
  const tr = data.trend || {};
  const trendText =
    tr.direction === 'rising' ? '↗ Getting worse' : tr.direction === 'falling' ? '↘ Getting better' : tr.direction === 'steady' ? '→ Steady' : 'Trend unknown';
  const h = data.health || {};
  const top = (data.top3 || []).map((id) => (h.actions || []).find((a) => a.id === id)).filter(Boolean);
  const rest = (h.actions || []).filter((a) => !(data.top3 || []).includes(a.id));
  return (
    <View>
      <Card>
        <H2>{stale ? 'Last available week' : 'This week'}</H2>
        {stale ? <Banner kind="danger">Data feed stopped: this is the newest week with data, not the current week.</Banner> : null}
        {!data.enough ? (
          <Muted>Not enough data for a weekly summary (needs at least 5 of 7 days with valid data).</Muted>
        ) : (
          <View>
            <View style={st.summary}>
              <View style={{ flex: 1 }}>
                <Text style={st.big}>{bad + ' of 7'}</Text>
                <Muted>days Moderate or worse</Muted>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={st.trend}>{trendText}</Text>
                <Muted>{tr.last3 != null ? 'last 3 days avg ' + tr.last3 + ' vs ' + tr.prev4 : ''}</Muted>
              </View>
            </View>
            <View style={st.bars}>
              {days.map((d) => (
                <View key={d.date} style={st.dayCol}>
                  <Text style={st.dayAqi}>{d.valid ? d.aqi : '–'}</Text>
                  <View style={st.track}>
                    <View
                      style={[
                        st.dayBar,
                        d.valid
                          ? { height: ((d.aqi || 0) / max) * 110, backgroundColor: catStyle(d.category).bg }
                          : { height: 6, backgroundColor: '#d5dbe2' },
                      ]}
                    />
                  </View>
                  <Text style={st.dayLbl}>{d.weekday}</Text>
                  <Text style={st.dayLbl2}>{d.label}</Text>
                </View>
              ))}
            </View>
            {data.dominant ? <Muted style={{ marginTop: 8 }}>{'Main pollutant this week: ' + pname(data.dominant)}</Muted> : null}
          </View>
        )}
      </Card>

      {data.enough ? (
        <View>
          {(h.clean || []).length ? (
            <Card accent={catStyle('Good').bg}>
              <H2>Good news</H2>
              {h.clean.map((x) => (
                <Rich key={x.id} text={x.marked || x.text} style={[s.body, { marginBottom: 6 }]} />
              ))}
            </Card>
          ) : null}
          {top.length ? (
            <Card accent={C.teal}>
              <H2>Your top actions this week</H2>
              {top.map((a) => (
                <ActionRow key={a.id} icon={a.icon} marked={a.marked} text={a.text} source={'[' + a.sources.join('][') + ']'} />
              ))}
            </Card>
          ) : null}
          {(h.short_term || []).length ? (
            <Card accent={catStyle('Moderate').bg}>
              <H2>{stale ? 'During that week, air like this may affect you' : 'This week, air like this may affect you'}</H2>
              {h.short_term.map((x) => (
                <Item key={x.id} x={x} />
              ))}
            </Card>
          ) : null}
          {(h.long_term || []).length ? (
            <Card accent={catStyle('Very Poor').bg}>
              <H2>If this continues</H2>
              {h.long_term.map((x) => (
                <Item key={x.id} x={x} />
              ))}
            </Card>
          ) : null}
          {rest.length ? (
            <Card>
              <H2>More things you can do</H2>
              {rest.map((a) => (
                <ActionRow key={a.id} icon={a.icon} marked={a.marked} text={a.text} source={'[' + a.sources.join('][') + ']'} />
              ))}
            </Card>
          ) : null}
        </View>
      ) : null}
      <Muted style={{ textAlign: 'center', marginVertical: 8 }}>{data.disclaimer}</Muted>
    </View>
  );
}

function Item({ x }) {
  return (
    <View style={{ paddingVertical: 6 }}>
      <Rich text={'• ' + (x.marked || x.text)} style={s.body} />
      <Text style={s.src}>{'[' + (x.sources || []).join('][') + ']'}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  summary: { flexDirection: 'row', marginBottom: 14 },
  big: { fontSize: 28, fontWeight: '800', color: C.text },
  trend: { fontSize: 18, fontWeight: '700', color: C.text, marginTop: 6 },
  bars: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' },
  dayCol: { flex: 1, alignItems: 'center' },
  dayAqi: { fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 2 },
  track: { height: 112, justifyContent: 'flex-end', width: '70%' },
  dayBar: { width: '100%', borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  dayLbl: { fontSize: 12, color: C.text, marginTop: 4, fontWeight: '600' },
  dayLbl2: { fontSize: 10, color: C.muted },
});
