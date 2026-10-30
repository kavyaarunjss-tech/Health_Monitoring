# Health Advisory Reference (for the AQI alert website)

Every threshold and message shown to users must trace to a source below. Personal alert thresholds are a
design decision derived from these sources (not official alert triggers); say so in the paper.

## 1. CPCB AQI categories and health impacts
| Category | AQI | Associated health impacts, CPCB [1] Table 3.12 (word for word) | Source shown on the site | Possible health consequences, NCDC [3] |
|---|---|---|---|---|
| Good | 0–50 | Minimal Impact | [1][2] | Low risk |
| Satisfactory | 51–100 | May cause minor breathing discomfort to sensitive people | [1][2] | Minor breathing discomfort in vulnerable populations |
| Moderate | 101–200 | May cause breathing discomfort to the people with lung disease such as asthma and discomfort to people with heart disease, children and older adults | [1] | Breathing or other health discomforts in vulnerable populations |
| Poor | 201–300 | May cause breathing discomfort to people on prolonged exposure and discomfort to people with heart disease with short exposure | [1] | Breathing discomfort in healthy people; breathing or other health discomforts in vulnerable populations |
| Very Poor | 301–400 | May cause respiratory illness to the people on prolonged exposure. Effect may be more pronounced in people with lung and heart diseases | [1][2] | Respiratory illness in healthy people; severe breathing illnesses in vulnerable population |
| Severe | 401–500 | May cause respiratory effects even on healthy people and serious health impacts on people with lung/heart diseases. The health impacts may be experienced even during light physical activity | [1] | Respiratory illness in healthy people; severe breathing illnesses in vulnerable population |

Checked 26 Oct 2026 in the official CPCB report [1] (https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf), Table 3.12 "Health Statements for AQI
Categories", printed p. 36 (PDF p. 38). The site shows these sentences exactly (advice.py `IMPACT`; test `backend/test_category_statements.py`). [2] (Arthapedia,
page checked 26 Oct 2026) is cited as well only where its wording is identical (Good, Satisfactory, Very Poor). Differences in [2]: Moderate "to people with
lung disease such as asthma, and discomfort" ([1]: "to the people ... asthma and discomfort"); Poor without "with short exposure"; Severe "respiratory impact
... lung/heart disease" ([1]: "respiratory effects ... lung/heart diseases"). Until 26 Oct 2026 the site used the [2] wording; the NCDC [3] column was checked
on the scanned handbook p. 31 the same day.

## 2. Vulnerable groups (profile options)
Lung disease (asthma/COPD), heart disease, child (< 14; [3] says < 5, [4] says < 14), older adult, pregnant,
outdoor worker, athlete/regular outdoor exerciser [3][4][5]. Healthy adult = general population.

Age rules for user accounts (website): age < 14 is marked "Child" automatically (follows [4]); age >= 60 is marked "Older adult" automatically. **60 is a design choice of this project**: the sources name older adults as a vulnerable group but give no age cut-off.

## 3. Personal alert thresholds (design decision)
| User group | Advisory from | Alert (pop-up/push) from | Basis |
|---|---|---|---|
| Vulnerable | Satisfactory, AQI ≥ 51 | Moderate, AQI ≥ 101 | Effects in sensitive people from Satisfactory [1][2]; vulnerable advice from Satisfactory [3]; Moderate names these groups [1][2] |
| Healthy adult | Moderate, AQI ≥ 101 | Poor, AQI ≥ 201 | General advice from Moderate [3]; discomfort in healthy people from Poor [3] |
| Everyone | — | Very Poor, AQI ≥ 301 | Respiratory illness in healthy people; N95/N99 advice begins [3] |
Users may lower their thresholds, never raise them above these defaults.

## 4. Category-wise messages [3] (quote these)
| Category | General population | Vulnerable population |
|---|---|---|
| Good | No special precautions | No special precautions |
| Satisfactory | No need for special precautions | Use face masks/cloth/scarves to cover the nose while going out; avoid physical exertion for long periods |
| Moderate | Use mask or cloth to cover nose; avoid physical exertion for long periods | Use face masks/cloth/scarves to cover the nose while going out; avoid physical exertion for long periods; take frequent water breaks between work |
| Poor | Avoid outdoor physical exertion, if possible; take frequent water breaks between work; use mask/cloth to cover nose while going out | Use face masks/scarves to cover the nose while going out; avoid heavy exertion when outside and take lots of water breaks; in a closed space keep external doors and windows closed but ensure sufficient ventilation |
| Very Poor | Avoid outdoor physical activities; avoid additional pollution sources (burning, candles, smoking indoors); use a close-fitted N95 or N99 mask while going out | Remain indoors as much as possible and keep activity levels low; use a close-fitted N95 or N99 mask while going out; take a healthy diet and lots of water; avoid indoor pollution sources |
| Severe | Avoid outdoor physical activities; use a close-fitted N95 or N99 mask while going out; avoid indoor pollution sources; drink lots of water | Remain indoors and keep activity levels low; avoid indoor pollution sources; always use a close-fitted N95 or N99 mask while stepping outside; step out only if urgent |

## 5. Cross-cutting advice
| Advice | When | Source |
|---|---|---|
| Keep prescribed medicines readily available and follow your doctor's instructions; seek medical advice promptly if symptoms worsen | Lung/heart profiles, at Alert | [4] |
| Consult the nearest doctor for breathlessness, giddiness, cough, chest discomfort or pain | All users, at Alert | [4] |
| On poor to severe days, avoid outdoor morning and late-evening walks, runs, jogging and exercise | Poor and above | [4] |
| Practise wet mopping instead of sweeping | Poor and above | [4] |
| Avoid air purifiers that generate ozone | With any purifier suggestion | [4][5] |
| Paper masks, handkerchiefs, scarves and cloth are not effective in poor to severe pollution | Poor and above, with mask advice | [3][4] |
| Plan when and where to be active (cleaner hours, away from traffic) rather than stopping activity | Best-time planner | [5] |

WHO cautions to show beside mask advice [5] (checked again on 25 Oct 2026 in the page HTML, question "Can respirators be recommended as a public health
measure?" and "Can respirators protect from air pollution in the occupational setting?"): "Given the limited evidence on the effectiveness of respirators to
protect health in real conditions of use by the general population, their use should not be recommended."; "Because of differences in facial structures across
the world, no one respirator can be guaranteed to fit all users. There are no commercial respirators designed for children (based on information available as of
February 2019)."; "a special caution is necessary for people with respiratory and cardiovascular disease for whom it may not be advisable to use a respirator due
to increased dead space, airway resistance and psychological stress." (The earlier wording "ask their doctor" is NOT in the WHO text and was removed.)

Do NOT say: "use an N95" below Very Poor; "keep your reliever inhaler" (no Indian source names inhalers).

Example message: "AQI at Silk Board is forecast to reach 160 (Moderate, mainly PM10) between 6 and 10 pm.
Because you have asthma: cover your nose when you go out, avoid physical exertion for long periods, and keep
your prescribed medicines readily available [3][4]. Consult a doctor if you feel breathless or have chest
discomfort [4]. Cleanest time for your walk tomorrow: 9–11 am (forecast AQI 70) [5]."

## 6. Disclaimer (show on profile page, footer, and linked in every alert)
> **Health information disclaimer.** AQI forecasts on this site are produced by a statistical model and can be
> wrong. The health messages are general guidance based on the Central Pollution Control Board's National Air
> Quality Index and the Ministry of Health and Family Welfare's air-pollution advisories, with cautions from the
> World Health Organization. They are not medical advice and do not replace advice from your doctor. If you have
> a health condition, follow the plan your doctor has given you. Seek medical help promptly if you experience
> breathlessness, chest pain, dizziness or other worsening symptoms. In an emergency, call 112.

## 7. Personalised advice parts (website, 20 Oct 2026; `backend/advice.py personal_advice`)
Each alert / "For you" line / e-mail is built from parts. Every health statement carries its source; the trend and best-time lines are our
own forecast output and are labelled "(our forecast)". Passages were checked in the source documents on 20 Oct 2026 (page = printed page).

| Part | Wording used (shortened) | Source |
|---|---|---|
| Headline | Category + CPCB health impact (section 1) | [1][2] |
| What to do | Category message, general or vulnerable column (section 4) | [3] |
| Lung / heart disease | Advice only (the CPCB impact sentence naming the group is already the headline line, so it is not repeated): Satisfactory / Moderate: "Persons with airway, lung or heart illnesses should keep their medications readily available" (poster p. 39) and "Properly follow personal doctor's instructions on healthcare" (p. 44); Poor: "Avoid outdoor physical activities" (vulnerable population, Poor 201-300: poster p. 38 and Appendix 1 table p. 57) + medicines; Very Poor / Severe: "Remain indoors and keep activity levels low" (pp. 38, 57), "Keep a check on exacerbations of symptoms", "Seek immediate medical advice if symptoms worsen" (advisory pp. 44-45) | [4] |
| Child / older adult | Advice only (headline already says Moderate air may cause discomfort to children and older adults [1][2]). NCDC advice for the vulnerable population ("Elderly, children under 5 years, pregnant women, pre-existing illnesses like asthma and other airway or lung (respiratory) and heart (cardiovascular) diseases", p. 57) by category: Satisfactory "Reduce prolonged or strenuous outdoor physical exertion" (pp. 38, 42), Moderate "Avoid prolonged or strenuous outdoor physical exertion" (pp. 38, 42, 57), Poor "Avoid outdoor physical activities" (pp. 38, 57; the poster on p. 42 has the milder "Avoid outdoor physical exertion" for Poor), Very Poor / Severe "Remain indoors and keep activity levels low" (pp. 38, 43, 57). **Checked 21 Oct 2026: "avoid outdoor physical activities" is the Poor level in [4], not Very Poor.** Child at Very Poor+: "There are no commercial respirators designed for children (based on information available as of February 2019)" [5] | [4] ([5]) |
| Pregnancy | WHO: pregnant women are among the groups at higher risk ("Children & Pregnant women") [5]; same NCDC vulnerable-population action by category [4] | [5][4] |
| Outdoor work | WHO: "populations at specific risk (due to their health status or occupation) should be advised about the best time and location for physical activity or for work (e.g. outdoors)" [5]; "take frequent water breaks between work" (Moderate), "avoid heavy exertion when outside and take lots of water breaks" (Poor), N95/N99 only from Very Poor [3] | [5][3] |
| Regular exercise | WHO: "regular physical activity should be promoted even if the local air quality is not optimal"; "adapt the timing and location of physical activity to reduce exposure" [5]; Poor+: "On days with poor to severe AQI, avoid outdoor morning and late evening walk, run, jog and physical exercise", "Reschedule outdoor activities as per AQI level" (advisory p. 44) [4] | [5][3][4] |
| Trend | Rising / falling / steady, worst or best of the +1/+6/+12/+24 h forecasts | (our forecast) |
| Best time to go out | NOT from the AQI forecast points (CPCB AQI is a 24 h average). The station's typical time-of-day pattern: median hourly PM2.5 and PM10 per hour of the day over the 28 days before the current / simulated hour (only data available then; measured hours only). Shown as "Usually cleanest at this station: 1-4 pm; usually worst: 7-10 pm (typical pattern from the last 4 weeks, not a forecast)" only if the cleanest daytime (6 am-9 pm) 3-hour block is >= 20% lower than the worst 3-hour block and each of those hours has data on >= 20 of 28 days; otherwise "No clearly better time at this station". Very Poor / Severe: "Limit outdoor activity at all times" ([3]: Very Poor/Severe messages "Avoid outdoor physical activities", "Remain indoors"). Design rule of this project; WHO: plan when and where to be active [5] | [5] or (station data); [3] |
| Main pollutant | Exact sentences, checked on the pages on 21 Oct 2026. [6] (https://www.who.int/news-room/spotlight/how-air-pollution-is-destroying-our-health, no date on the page): "Particles with a diameter of 10 microns or less (≤ PM10) can penetrate and lodge deep inside the lungs, causing irritation, inflammation and damaging the lining of the respiratory tract." / "Smaller, more health-damaging particles with a diameter of 2.5 microns or less (≤ PM2.5 – 60 of them make up the width of a human hair) can penetrate the lung barrier and enter the blood system, affecting all major organs of the body." / "nitrogen dioxide (NO2), a gas from combustion of fuels in processes such as those used for furnaces, gas stoves, transportation, industry and power generation; sulfur dioxide, another gas mainly from the combustion of fossil fuels for domestic heating, industries and power generation; and ozone at ground level, caused by a chemical reaction of gases, such as NO2, in the presence of sunlight." / "Ozone is a major factor in causing asthma (or making it worse) ...". [7] (https://www.who.int/news-room/fact-sheets/detail/ambient-(outdoor)-air-quality-and-health, published 24 Oct 2024): "NO2 is a gas that is commonly released from the combustion of fuels in the transportation and industrial sectors." / "Carbon monoxide is a colourless, odourless and tasteless toxic gas produced by the incomplete combustion of carbonaceous fuels such as wood, petrol, charcoal, natural gas and kerosene." The site's lines follow this wording (e.g. PM2.5: "smaller, more health-damaging particles 2.5 microns or less across (60 of them make up the width of a human hair); they can penetrate the lung barrier and enter the blood system"). Hedged on 26 Oct 2026 (site wording, not the quotes): PM10 "they can penetrate and lodge deep inside the lungs, which can cause irritation and inflammation"; ozone "WHO calls it a major factor in causing asthma or making it worse". | [6][7] |
| Rotating tip (one per alert; chosen by the alert number = issue hour, so the same alert always shows the same tip; profile-specific tips first) | Exact list below ("Tips"). Items from the NCDC advisory (pp. 44-45, written for severe-plus AQI) only from Poor or Very Poor; N95/N99 only from Very Poor and never for a child. | see list |
| Doctor | At alert level: "Consult the nearest doctor in case of breathlessness, giddiness, cough, chest discomfort or pain, irritation in the eyes" (p. 39, p. 44) | [4] |
| Caution | WHO respirator cautions (section 5), from Very Poor | [5] |

Pop-up: the forecast line (headline) plus 1-2 profile lines, trend, best time (or "no clear time" / "limit outdoor activity") and 1 tip. E-mail and Health advice tab: all parts, with a "How is this calculated?" note for the best time.

Tips (exact wording used; lowest category; who):
| Tip | From | For | Source |
|---|---|---|---|
| Take frequent water breaks between work | Moderate | outdoor workers | [3] (vulnerable, Moderate) |
| Adapt the timing and location of your exercise to reduce exposure | Satisfactory | regular exercisers | [5] |
| There are no commercial respirators designed for children (based on information available as of February 2019) | Very Poor | children | [5] |
| WHO advises special caution with respirators for people with heart or lung disease | Very Poor | lung / heart disease | [5] |
| Check the air quality index before leaving home | Satisfactory | everyone | [4] p. 35 |
| Avoid going to places with heavy traffic and congested areas | Satisfactory | everyone | [4] pp. 35-36, 40 |
| Use clean smokeless fuels (gas or electricity) for cooking and heating | Satisfactory | everyone | [4] p. 39 |
| Don't burn firecrackers, wood, leaves or garbage | Satisfactory | everyone | [4] p. 39 |
| Don't smoke cigarettes, bidis or other tobacco products | Satisfactory | everyone | [4] p. 39 |
| Keep doors and windows closed in the early morning and late evening; ventilate in the afternoon (12 to 4 pm) | Poor | everyone | [4] pp. 39, 44 |
| Practise wet mopping instead of sweeping | Poor | everyone | [4] p. 44 |
| Avoid burning mosquito coils and incense sticks in closed rooms | Poor | everyone | [4] p. 44 |
| Paper masks, handkerchiefs, scarves and cloth are not effective in poor to severe pollution | Poor | everyone | [3][4] |
| Use a close-fitted N95 or N99 mask while going out (see the WHO caution below) | Very Poor | everyone except children | [3] |
| Keep washing your eyes with running water and gargle regularly with warm water | Very Poor | everyone | [4] p. 44 |
| Eat a healthy diet and drink plenty of water | Very Poor | everyone | [3][4] |
| If you use an air purifier, avoid one that works by generating ozone | Very Poor | everyone | [4] p. 45, [5] |
| Use the air conditioner (home or car) in re-circulate mode | Very Poor | everyone | [4] p. 45 |
E-mail and Health advice tab: all parts. Not used: any group advice not found in these sources (e.g. no inhaler advice, no N95 below Very Poor).

## 8. Weekly summary "This week's air and your health" (25 Oct 2026; `backend/weekly.py`, `backend/weekly_advice_rules.json`)
Sources checked on 25 Oct 2026 in the original documents (page = printed page).

**Limits used for "days above"** (comparison of each day's value with the limit; a day counts only with >= 16 of 24 valid hours):
| Pollutant | India NAAQS 2009 [9] (Industrial, Residential, Rural and Other Area) | WHO 2021 AQG level [8] (Table 0.1, executive summary p. 4) |
|---|---|---|
| PM2.5 | 60 µg/m³, 24 hours | 15 µg/m³, 24-hour |
| PM10 | 100 µg/m³, 24 hours | 45 µg/m³, 24-hour |
| NO2 | 80 µg/m³, 24 hours | 25 µg/m³, 24-hour |
| SO2 | 80 µg/m³, 24 hours | 40 µg/m³, 24-hour |
| O3 | 100 µg/m³, 8 hours (daily maximum 8 h mean) | 100 µg/m³, 8-hour (daily maximum 8 h mean) |
| CO | 2 mg/m³, 8 hours (daily maximum 8 h mean) | 4 mg/m³, 24-hour (daily 24 h mean) |

- [9] footnote (p. 4): "24 hourly or 08 hourly or 01 hourly monitored values, as applicable, shall be complied with 98% of the time in a year. 2% of the time, they may exceed the limits but not on two consecutive days."
- [8] Table 0.1 footnote a: "99th percentile (i.e. 3–4 exceedance days per year)." Executive summary p. 1: "Air pollution increases morbidity and mortality from cardiovascular and respiratory disease and from lung cancer."
- [7] Key fact: "Air pollution is one of the greatest environmental risks to child health"; "some 68% of outdoor air pollution related premature deaths were due to ischaemic heart disease and stroke, 14% were due to chronic obstructive pulmonary disease, 14% were due to acute lower respiratory infections, and 4% of deaths were due to lung cancers."
- [1] (CPCB National AQI report, official PDF https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf, read 26 Oct 2026), Table 3.12 "Health Statements for AQI Categories", printed p. 36 (PDF page 38): Satisfactory (51–100) "May cause minor breathing discomfort to sensitive people". C3 matches it word for word and cites [1][2][3]. (The old link app.cpcbccr.com, accessed 26 Oct 2026, serves an HTML page with third-party ads, not the PDF; not used.)
- [2] (Arthapedia, page HTML checked 26 Oct 2026): "Satisfactory (51–100) May cause minor breathing discomfort to sensitive people."
- [3] (ASHA handbook 2024, read from the scanned PDF on 26 Oct 2026), printed p. 31, Chapter 03 table "AQI Levels, Health Effects and Protective Health Measures": Satisfactory, Possible Health Consequences "May cause: Minor breathing discomfort in vulnerable populations"; Moderate "Breathing or other health discomforts in vulnerable populations"; Poor "Breathing discomfort in healthy people"; Moderate, Messages for Vulnerable Population "Ensure taking frequent water breaks between work"; Poor, Messages for General Population "Take frequent water breaks between work". This is the air-pollution AQI table (not heat advice), so A10 stays.
- [4] (Health Adaptation Plan 2021): p. vii "Those with underlying medical problems like heart disease, respiratory disorder, pregnant women, outdoor workers, the elderly, children under age 14, and athletes are more vulnerable to air pollution." p. 6 Table 2, short-term: "Respiratory & cardiovascular emergency department visits ... hospital admissions ... Days of restricted activity"; long-term: "Chronic respiratory diseases incidence & prevalence (asthma, COPD, chronic pathological changes)", "Chronic cardiovascular diseases", "Intrauterine growth restrictions (low birth weight at term, intrauterine growth retardation, small for gestational age)", "Lung cancers". p. 25 (AQI Moderate to Poor) "Clinical manifestation: Acute Respiratory Illnesses, Dust Allergies, Asthma exacerbation, Rhino-ocular symptoms, Cardiovascular problems- Acute Coronary Syndrome". p. 41 poster: "SHORT TERM EFFECTS: Headache, Giddiness; Irritation in eyes; Coughing; Breathlessness; Skin Irritation" / "LONG TERM EFFECTS: Central Nervous System (Stroke); Cardiovascular Diseases (Heart Attack); Respiratory Diseases (Asthma, Bronchitis); Lung Cancer Risk". p. 38 / p. 57 advice table (general / vulnerable population): Moderate "Reduce / Avoid prolonged or strenuous outdoor physical exertion", Poor "Avoid outdoor physical exertion / Avoid outdoor physical activities", Very Poor and Severe (vulnerable) "Remain indoors and keep activity levels low".

**Rules** (design decisions): week = 7 complete calendar days before the replay clock / newest live observation; >= 5 valid days needed, otherwise "Not enough data for a weekly summary" and no health statements; persistent = >= 4 of the 7 days with AQI >= 101; trend = mean of the last 3 days vs the previous 4, steady unless the change exceeds max(10 AQI points, 10 %); long-term statements only for persistent weeks; all statements hedged ("may", "is linked to", "at higher risk"); never a diagnosis. Statements and actions:

| id | section | condition | groups | text | sources | basis (exact wording / page) |
|---|---|---|---|---|---|---|
| C1 | Clean week | clean week | all | Good news: no day this week reached Moderate or worse on the CPCB AQI scale. | [1] | CPCB category bands [1]; our daily AQI |
| C2 | Clean week | clean week | healthy | At Good and Satisfactory levels no special precautions are needed for the general population. | [3] | [3] category messages, general population, Good/Satisfactory |
| C3 | Clean week | clean week; worst day Satisfactory | lung, heart, child, older, pregnant, outdoor_work, exercise | At Satisfactory levels, air may cause minor breathing discomfort to sensitive people. | [1][2][3] | [1] CPCB report Table 3.12 'Health Statements for AQI Categories' (printed p. 36): 'Satisfactory (51–100) May cause minor breathing discomfort to sensitive people'; [2] Arthapedia AQI table: 'Satisfactory (51–100) May cause minor breathing discomfort to sensitive people.'; [3] ASHA handbook 2024 p. 31 table, Satisfactory: 'May cause: Minor breathing discomfort in vulnerable populations' |
| S1 | Short-term (this week) | episode/persistent; >= Moderate (healthy adults: >= Poor) | all | On polluted days, short-term exposure may cause headache, giddiness, eye irritation, coughing or breathlessness. | [4] | [4] HAP 2021 p. 41 poster 'Short term effects: Headache, Giddiness; Irritation in eyes; Coughing; Breathlessness; Skin Irritation'. Shown to vulnerable groups from Moderate, to healthy adults only from Poor (design, following the category impacts: Moderate 'Breathing or other health discomforts in vulnerable populations', Poor 'Breathing discomfort in healthy people' [3] p. 31; CPCB Moderate names sensitive groups [2]) |
| S2 | Short-term (this week) | episode/persistent; >= Moderate | lung | People with lung disease such as asthma or COPD are at higher risk: Moderate air may cause them breathing discomfort, and Moderate to Poor air is linked to asthma attacks and acute respiratory illness. | [1][2][4] | [1] Moderate 'breathing discomfort to the people with lung disease such as asthma'; [2] Moderate 'breathing discomfort to people with lung disease such as asthma'; [4] p. 25 Moderate to Poor 'Acute Respiratory Illnesses ... Asthma exacerbation' |
| S3 | Short-term (this week) | episode/persistent; >= Moderate | heart | People with heart disease are at higher risk: Moderate to Poor air may cause them discomfort and is linked to heart problems such as acute coronary syndrome. | [1][2][4] | [1][2] Moderate and Poor impact 'discomfort to people with heart disease'; [4] p. 25 'Cardiovascular problems- Acute Coronary Syndrome' |
| S4 | Short-term (this week) | episode/persistent; >= Moderate | child | Children are among the groups at higher risk: WHO counts air pollution among the greatest environmental risks to child health, and Moderate air may cause discomfort to children. | [7][1][2] | [7] key fact 'Air pollution is one of the greatest environmental risks to child health'; [1][2] Moderate impact names children |
| S5 | Short-term (this week) | episode/persistent; >= Moderate | older | Older adults are among the groups at higher risk: Moderate air may cause discomfort to older adults. | [1][2][4] | [1][2] Moderate impact names older adults; [4] p. vii 'the elderly ... more vulnerable' |
| S6 | Short-term (this week) | episode/persistent; >= Moderate | pregnant | Pregnant women are among the groups more vulnerable to air pollution. | [4][5] | [4] p. vii 'pregnant women ... are more vulnerable to air pollution'; [5] 'Children & Pregnant women' |
| S7 | Short-term (this week) | episode/persistent; >= Moderate | outdoor_work, exercise | Outdoor workers and people who exercise outdoors are among the groups more vulnerable to air pollution. | [4][5] | [4] p. vii 'outdoor workers ... and athletes are more vulnerable'; [5] 'Outdoor workers' |
| S8 | Short-term (this week) | episode/persistent; >= Poor | all | Poor air may cause breathing discomfort even in healthy people on prolonged exposure. | [1][2][3] | [1][2] Poor 'breathing discomfort to people on prolonged exposure'; [3] Poor 'Breathing discomfort in healthy people' |
| S9 | Short-term (this week) | episode/persistent; >= Very Poor | all | Very Poor air may cause respiratory illness on prolonged exposure, with effects more pronounced in people with lung and heart disease. | [1][2] | [1][2] Very Poor impact |
| S10 | Short-term (this week) | episode/persistent; >= Moderate; main pollutant pm25 | all | This week's main pollutant was PM2.5: fine particles that can penetrate the lung barrier and enter the blood system. | [6] | [6] '... (≤ PM2.5 ...) can penetrate the lung barrier and enter the blood system' |
| S11 | Short-term (this week) | episode/persistent; >= Moderate; main pollutant pm10 | all | This week's main pollutant was PM10: particles that can penetrate and lodge deep inside the lungs, which can cause irritation and inflammation. | [6] | [6] '(≤ PM10) can penetrate and lodge deep inside the lungs, causing irritation, inflammation ...' |
| S12 | Short-term (this week) | episode/persistent; >= Moderate; main pollutant o3 | lung | This week's main pollutant was ground-level ozone, which WHO calls a major factor in causing asthma or making it worse. | [6] | [6] 'Ozone is a major factor in causing asthma (or making it worse)' |
| L1 | Long-term awareness (persistent weeks only) | persistent | all | Sustained exposure over months and years is linked to heart disease, stroke, chronic lung disease such as COPD, and lung cancer. | [7][8][4] | [7] deaths 'due to ischaemic heart disease and stroke ... chronic obstructive pulmonary disease ... lung cancers'; [8] executive summary p. 1 'Air pollution increases morbidity and mortality from cardiovascular and respiratory disease and from lung cancer'; [4] p. 41 long-term effects |
| L2 | Long-term awareness (persistent weeks only) | persistent | lung | Long-term exposure is linked to the development and worsening of chronic respiratory diseases such as asthma and COPD. | [4] | [4] p. 6 Table 2, long-term 'Chronic respiratory diseases incidence & prevalence (asthma, COPD, chronic pathological changes)' |
| L3 | Long-term awareness (persistent weeks only) | persistent | heart | Long-term exposure is linked to chronic cardiovascular disease, including heart attack. | [4] | [4] p. 6 'Chronic cardiovascular diseases'; p. 41 'Cardiovascular Diseases (Heart Attack)' |
| L4 | Long-term awareness (persistent weeks only) | persistent | pregnant | Sustained exposure during pregnancy is linked to restricted growth of the baby before birth (low birth weight). | [4] | [4] p. 6 long-term 'Intrauterine growth restrictions (low birth weight at term, intrauterine growth retardation, small for gestational age)' |
| A1 | What you can do | episode/persistent; >= Moderate | healthy | On Moderate days, reduce prolonged or strenuous outdoor physical exertion. | [4] | [4] p. 38 general population, Moderate |
| A2 | What you can do | episode/persistent; >= Moderate | lung, heart, child, older, pregnant, outdoor_work, exercise | On Moderate days, avoid prolonged or strenuous outdoor physical exertion. | [4] | [4] p. 38 vulnerable population, Moderate |
| A3 | What you can do | episode/persistent; >= Poor | lung, heart, child, older, pregnant, outdoor_work, exercise | On Poor days, avoid outdoor physical activities. | [4] | [4] pp. 38, 57 vulnerable population, Poor |
| A4 | What you can do | episode/persistent; >= Poor | healthy | On Poor days, avoid outdoor physical exertion. | [4] | [4] p. 38 general population, Poor |
| A5 | What you can do | episode/persistent; >= Very Poor | lung, heart, child, older, pregnant, outdoor_work, exercise | On Very Poor or Severe days, remain indoors and keep activity levels low. | [4] | [4] pp. 38, 43, 57 vulnerable population |
| A6 | What you can do | episode/persistent; >= Moderate | all | Plan outdoor activity for cleaner hours (see 'Usually cleanest at this station'); WHO advises adapting the timing and location of physical activity to reduce exposure. | [5] | [5] 'adapt the timing and location of physical activity to reduce exposure' |
| A7 | What you can do | episode/persistent; >= Moderate | lung, heart | Keep your prescribed medicines readily available and follow your doctor's instructions. | [4] | [4] p. 39 'Persons with airway, lung or heart illnesses should keep their medications readily available'; p. 44 'Properly follow personal doctor's instructions' |
| A8 | What you can do | episode/persistent; >= Poor | all | Keep doors and windows closed in the early morning and late evening; ventilate in the afternoon (12 to 4 pm). | [4] | [4] pp. 39, 44 |
| A9 | What you can do | episode/persistent; >= Moderate | all | Avoid going to places with heavy traffic and congested areas. | [4] | [4] pp. 35-36, 39-40 |
| A10 | What you can do | episode/persistent; >= Moderate | outdoor_work | If you work outdoors, take frequent water breaks between work. | [3] | [3] ASHA handbook 2024 p. 31, Chapter 03 table 'AQI Levels, Health Effects and Protective Health Measures' (air pollution, not heat advice), Moderate, Messages for Vulnerable Population: 'Ensure taking frequent water breaks between work'; Poor, general population: 'Take frequent water breaks between work' |
| A11 | What you can do | episode/persistent; >= Very Poor | all (not child) | On Very Poor or Severe days use a close-fitted N95 or N99 mask while going out. WHO cautions that no one respirator can be guaranteed to fit all users, and that people with lung or heart disease need special caution. | [3][5] | [3] Very Poor/Severe messages; [5] respirator cautions |
| A12 | What you can do | episode/persistent; >= Very Poor | child | There are no commercial respirators designed for children (based on information available as of February 2019); keep children indoors with low activity on Very Poor or Severe days. | [5][4] | [5] question 'Can respirators protect from air pollution in the occupational setting?': 'There are no commercial respirators designed for children (based on information available as of February 2019)'; [4] vulnerable population 'Remain indoors and keep activity levels low' |
| A13 | What you can do | episode/persistent; >= Moderate | all | Use clean smokeless fuels (gas or electricity) for cooking and heating, and don't burn wood, leaves or garbage. | [4] | [4] p. 39 |
| A14 | What you can do | episode/persistent; >= Moderate | all | Consult the nearest doctor if you have breathlessness, giddiness, cough, chest discomfort or pain, or red or watery eyes. | [4] | [4] pp. 39, 44 'Consult the nearest doctor in case of breathlessness, giddiness, cough, chest discomfort or pain, irritation in the eyes (red or watery)' |

## References
1. Central Pollution Control Board. (2014). *National Air Quality Index* (CUPS/82/2014-15). MoEFCC, Government of India. https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf (official CPCB copy, PDF checked 26 Oct 2026: cover "Control of Urban Pollution Series CUPS/82/2014-15". The old link app.cpcbccr.com/ccr_docs/FINAL-REPORT_AQI_.pdf, accessed 26 Oct 2026, no longer serves the PDF but an HTML page with third-party advertising, so it is not used.)
2. Indian Economic Service. (n.d.). National Air Quality Index. *Arthapedia*. https://ies.gov.in/index.php/arthapedia/concept/national-air-quality-index
3. National Centre for Disease Control. (2024). *Air pollution and its impact on health: Handbook for ASHA* (NPCCHH). MoHFW. https://ncdc.mohfw.gov.in/uploads/pdf/air1.pdf
4. National Centre for Disease Control. (2021). *Health adaptation plan for diseases due to air pollution* (NPCCHH). MoHFW. https://ncdc.mohfw.gov.in/wp-content/uploads/2024/05/1.Health-Adaptation-Plan-for-Disease-Due-to-Air-Pollutions-2021.pdf
5. World Health Organization. (2024, October 4). *Air pollution: Personal interventions and risk communication*. https://www.who.int/news-room/questions-and-answers/item/air-pollution-personal-interventions-and-risk-communication
6. World Health Organization. (n.d.). *How air pollution is destroying our health* [Spotlight]. Retrieved October 20, 2026, from https://www.who.int/news-room/spotlight/how-air-pollution-is-destroying-our-health
7. World Health Organization. (2024, October 24). *Ambient (outdoor) air pollution* [Fact sheet]. https://www.who.int/news-room/fact-sheets/detail/ambient-(outdoor)-air-quality-and-health
8. World Health Organization. (2021). *WHO global air quality guidelines: particulate matter (PM2.5 and PM10), ozone, nitrogen dioxide, sulfur dioxide and carbon monoxide. Executive summary* (ISBN 978-92-4-003443-3). https://iris.who.int/handle/10665/345334 (full report: https://iris.who.int/handle/10665/345329)
9. Central Pollution Control Board. (2009, November 18). *National Ambient Air Quality Standards*, Notification No. B-29016/20/90/PCI-I. Gazette of India, Extraordinary, Part III, Section 4. https://cpcb.gov.in/uploads/National_Ambient_Air_Quality_Standards.pdf

Note on [4]: the PDF link above no longer resolves (404 on 20 Oct 2026). The same document (Health Adaptation Plan for Diseases due to Air Pollution,
NPCCHH, NCDC, MoHFW, July 2021) is at https://ncdc.mohfw.gov.in/uploads/pdf/air7.pdf; page numbers in section 7 are its printed page numbers.
