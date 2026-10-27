"""Independent Streamlit page for Eurostat Route Analytics v1. Run streamlit run app_eurostat.py"""
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Eurostat | Международные направления', layout='wide')
DATA=Path(__file__).parent/'data'
@st.cache_data
def read(name):
    return pd.read_csv(DATA/name, dtype={'geo':str,'partner':str,'time':str,'month_2026':str,'month_2025':str})

st.title('Eurostat · международные авианаправления')
st.caption('avia_paexcc · коммерческие пассажирские рейсы · FLIGHT / CAF_PAS / TOTAL · помесячно · 2025–2026')
st.info('Данные относятся к парам СТРАН, не аэропортов. Расчёт YoY выполнен только для пар, опубликованных в обоих годах. Отсутствие данных ≠ 0.')
try:
    panel=read('route_monthly_panel.csv'); pairs=read('route_pair_yoy.csv'); cov=read('route_coverage_monthly.csv')
except FileNotFoundError:
    st.error('Не найдены файлы в data/. Сначала выполните build_route_analytics.py.'); st.stop()

all_geos=sorted(panel.geo.unique()); all_partners=sorted(panel.partner.unique()); all_months=sorted(pairs.month_2026.unique())
with st.sidebar:
    st.header('Фильтры')
    month=st.selectbox('Месяц 2026', all_months,index=all_months.index('2026-03') if '2026-03' in all_months else 0)
    partners=st.multiselect('Страны-партнёры',all_partners,default=['IL','AE','QA','EG','TR','GE','AZ'])
    geos=st.multiselect('Отчитывающиеся страны',all_geos,default=all_geos)

subset=pairs[(pairs.month_2026==month)&pairs.partner.isin(partners)&pairs.geo.isin(geos)]
matched=subset[subset.comparable==True].copy()
num_all=len(subset);num_match=len(matched)
a,b,c=st.columns(3)
a.metric('Пар в фильтре',f'{num_all:,}')
b.metric('Сопоставимых пар',f'{num_match:,}')
c.metric('Доля сопоставимых',f'{100*num_match/num_all:.1f}%' if num_all else '—')

st.subheader('Изменения по странам-партнёрам')
if not matched.empty:
    summary=matched.groupby('partner',as_index=False).agg(pairs=('geo','size'),flights_2025=('flights_2025','sum'),flights_2026=('flights_2026','sum'))
    summary['difference']=summary.flights_2026-summary.flights_2025
    summary['yoy_pct']=summary.apply(lambda r:100*r.difference/r.flights_2025 if r.flights_2025>0 else float('nan'),axis=1)
    st.dataframe(summary.sort_values('yoy_pct'),use_container_width=True,hide_index=True)
    st.bar_chart(summary.set_index('partner')[['flights_2025','flights_2026']])
    st.download_button('Скачать таблицу выбранных направлений', summary.to_csv(index=False).encode('utf-8-sig'),file_name='eurostat_selected_matched_yoy.csv',mime='text/csv')
else:
    st.warning('Нет сопоставимых наблюдений при выбранных фильтрах.')

st.subheader('Покрытие публикации по месяцам')
st.line_chart(cov.set_index('time')['coverage_pct'])
st.caption('Процент опубликованных пар от 496 запрошенных. Поздние месяцы 2026 года могут быть неполными.')
st.dataframe(cov[['time','pairs_total','pairs_reported','reported_zeros','pairs_not_returned','coverage_pct']],use_container_width=True,hide_index=True)

with st.expander('Детальные пары стран и состояния отсутствующих значений'):
    st.dataframe(subset[['geo','partner','month_2025','month_2026','flights_2025','flights_2026','state_2025','state_2026','comparable','yoy_pct']].sort_values(['partner','geo']),use_container_width=True,hide_index=True)
with st.expander('Методологические ограничения'):
    st.markdown('''- Страновые пассажирские направления **не** измеряют маршрутную экспозицию конкретного аэропорта.
- Суммарные пассажирские рейсы Eurostat нельзя приравнивать к IFR-операциям EUROCONTROL.
- Сравниваем только одинаковые месяцы с двумя числовыми значениями; `0` допустим лишь когда возвращён API.
- Март 2026 включает другой временной интервал, чем первые 28 дней Event Study LLBG.
- Изменения направлений не доказывают отмены отдельных рейсов, причины изменений или перераспределение по FIR.''')
