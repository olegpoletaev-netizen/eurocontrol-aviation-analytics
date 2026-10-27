"""Embedded Eurostat panel for the main EUROCONTROL Streamlit app; local files only."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

@st.cache_data(show_spinner=False)
def _load_csv(path: str, mtime: int) -> pd.DataFrame:
    return pd.read_csv(path, dtype={'geo':'string', 'partner':'string', 'time':'string', 'month_2025':'string', 'month_2026':'string'})

COUNTRY_RU = {
    'IL':'Израиль', 'AE':'ОАЭ', 'QA':'Катар', 'EG':'Египет',
    'TR':'Турция', 'GE':'Грузия', 'AZ':'Азербайджан', 'SA':'Саудовская Аравия',
    'BH':'Бахрейн', 'KW':'Кувейт', 'IQ':'Ирак', 'JO':'Иордания',
    'LB':'Ливан', 'IR':'Иран', 'OM':'Оман', 'AT':'Австрия',
    'BE':'Бельгия', 'BG':'Болгария', 'CH':'Швейцария', 'CY':'Кипр',
    'CZ':'Чехия', 'DE':'Германия', 'DK':'Дания', 'EE':'Эстония',
    'EL':'Греция', 'FI':'Финляндия', 'FR':'Франция', 'HR':'Хорватия',
    'HU':'Венгрия', 'IE':'Ирландия', 'IS':'Исландия', 'IT':'Италия',
    'LT':'Литва', 'LU':'Люксембург', 'LV':'Латвия', 'MT':'Мальта',
    'NL':'Нидерланды', 'NO':'Норвегия', 'PL':'Польша', 'PT':'Португалия',
    'RO':'Румыния', 'SE':'Швеция', 'SI':'Словения', 'SK':'Словакия',
    'ES':'Испания', 'GR':'Греция', 'GB':'Великобритания'
}
def country_name(code):
    return f"{COUNTRY_RU.get(str(code), str(code))} ({code})"

def render_route_panel(data_dir: Path) -> None:
    st.subheader('Eurostat · международные направления')
    st.caption('avia_paexcc · CAF_PAS · FLIGHT · TOTAL · страны и страны-партнёры · январь 2025 — сентябрь 2026')
    st.info('Eurostat здесь показывает рейсы между СТРАНАМИ, а не аэропортами. Фильтр ICAO и даты в боковой панели относятся к EUROCONTROL и не применяются к этой вкладке.')
    required=['route_monthly_panel.csv','route_pair_yoy.csv','route_coverage_monthly.csv']
    missing=[name for name in required if not (data_dir/name).exists()]
    if missing:
        st.error('Отсутствуют файлы витрины Eurostat: '+', '.join(missing))
        st.code(str(data_dir))
        return
    panel,pairs,cov=[_load_csv(str(data_dir/n), (data_dir/n).stat().st_mtime_ns) for n in required]
    needed={'month_2026','partner','geo','comparable','flights_2025','flights_2026','state_2025','state_2026'}
    if not needed.issubset(pairs.columns):
        st.error('Некорректная структура route_pair_yoy.csv: '+str(sorted(needed-set(pairs.columns))))
        return
    months=sorted(pairs['month_2026'].dropna().unique().tolist())
    if not months:
        st.warning('В файле нет сравниваемых месяцев.')
        return
    col_m,col_p,col_g=st.columns([1,2,2])
    month=col_m.selectbox('Месяц сравнения с 2025 годом',months,index=months.index('2026-03') if '2026-03' in months else 0,key='es_month')
    partners=sorted(panel['partner'].dropna().unique().tolist())
    geos=sorted(panel['geo'].dropna().unique().tolist())
    selected_p=col_p.multiselect('Страны-партнёры',partners,default=[p for p in ['IL','AE','QA','EG','TR','GE','AZ'] if p in partners],key='es_partners',format_func=country_name)
    selected_g=col_g.multiselect('Отчитывающиеся страны',geos,default=geos,key='es_geo',format_func=country_name)
    subset=pairs.loc[pairs['month_2026'].eq(month)&pairs['partner'].isin(selected_p)&pairs['geo'].isin(selected_g)].copy()
    comparable=subset['comparable'].eq(True) | subset['comparable'].astype(str).str.lower().eq('true')
    matched=subset.loc[comparable & subset['flights_2025'].notna() & subset['flights_2026'].notna()].copy()
    a,b,c=st.columns(3)
    a.metric('Пар в фильтре',len(subset))
    b.metric('Пар с данными за оба года',len(matched))
    c.metric('Сопоставимость',f'{len(matched)/len(subset)*100:.1f}%' if len(subset) else '—')
    if matched.empty:
        st.warning('Нет числовых наблюдений для обеих сравниваемых дат при выбранных фильтрах.')
    else:
        summary=matched.groupby('partner',as_index=False).agg(matched_pairs=('geo','size'),flights_2025=('flights_2025','sum'),flights_2026=('flights_2026','sum'))
        summary['difference']=summary['flights_2026']-summary['flights_2025']
        summary['yoy_pct']=(summary['difference']/summary['flights_2025'].where(summary['flights_2025']>0))*100
        st.markdown('**Изменение числа коммерческих пассажирских рейсов по направлениям**')
        display=summary.sort_values('yoy_pct').copy()
        display['Страна-партнёр']=display['partner'].map(country_name)
        display=display.rename(columns={'matched_pairs':'Сопоставимых пар', 'flights_2025':'Рейсы 2025', 'flights_2026':'Рейсы 2026', 'difference':'Разница', 'yoy_pct':'Изменение, %'})
        st.dataframe(display[['Страна-партнёр','Сопоставимых пар','Рейсы 2025','Рейсы 2026','Разница','Изменение, %']],
                     use_container_width=True,hide_index=True,column_config={'Изменение, %':st.column_config.NumberColumn(format='%.1f%%')})
        chartdata=summary.copy()
        chartdata['Страна-партнёр']=chartdata['partner'].map(country_name)
        chartdata=chartdata.melt(id_vars='Страна-партнёр',value_vars=['flights_2025','flights_2026'],var_name='Год',value_name='Рейсы')
        chartdata['Год']=chartdata['Год'].map({'flights_2025':'2025','flights_2026':'2026'})
        fig=px.bar(chartdata,x='Страна-партнёр',y='Рейсы',color='Год',barmode='group')
        st.plotly_chart(fig,use_container_width=True)
        st.download_button('Скачать сопоставимые направления CSV',summary.to_csv(index=False).encode('utf-8-sig'),file_name='eurostat_route_selected_yoy.csv',mime='text/csv',key='es_download')
    st.markdown('**Покрытие публикации Eurostat**')
    cov=cov.sort_values('time')
    fig_cov=px.line(cov,x='time',y='coverage_pct',markers=True,labels={'time':'Месяц','coverage_pct':'Опубликованных пар, %'})
    st.plotly_chart(fig_cov,use_container_width=True)
    covshow=cov[['time','pairs_total','pairs_reported','reported_zeros','pairs_not_returned','coverage_pct']].rename(columns={
        'time':'Месяц','pairs_total':'Пар всего','pairs_reported':'Числовых пар','reported_zeros':'Опубликованных нулей',
        'pairs_not_returned':'Нет данных','coverage_pct':'Покрытие, %'})
    st.dataframe(covshow,hide_index=True,use_container_width=True,column_config={'Покрытие, %':st.column_config.NumberColumn(format='%.1f%%')})
    with st.expander('Исходные пары стран и статусы ячеек'):
        show=[c for c in ['geo','partner','month_2025','month_2026','flights_2025','flights_2026','state_2025','state_2026','comparable','yoy_pct'] if c in subset]
        details=subset[show].sort_values(['partner','geo']).copy()
        details=details.rename(columns={'geo':'Отчитывающаяся страна','partner':'Партнёр','month_2025':'Месяц 2025',
            'month_2026':'Месяц 2026','flights_2025':'Рейсы 2025','flights_2026':'Рейсы 2026',
            'state_2025':'Статус 2025','state_2026':'Статус 2026','comparable':'Сопоставимо','yoy_pct':'Изменение, %'})
        for col in ('Отчитывающаяся страна','Партнёр'):
            if col in details: details[col]=details[col].map(country_name)
        st.dataframe(details,hide_index=True,use_container_width=True)
    with st.expander('Методология Eurostat'):
        st.markdown('''- Используется показатель `CAF_PAS`, единица `FLIGHT`, расписание `TOTAL`; `SCHED` и `NSCHED` отдельно не суммируются с `TOTAL`.
- Сопоставляются одинаковые месяцы 2025 и 2026 года и **только одни и те же пары стран с двумя числовыми значениями**.
- `NOT_RETURNED` / отсутствующие ячейки **не заменяются нулём**. Подтверждённые API нули учитываются.
- Ряд `avia_paexcc` — уровень стран; прямого сопоставления с ежедневными аэропортовыми операциями EUROCONTROL нет.
- Изменение числа рейсов не доказывает причины, фактические перенаправления или изменения FIR-транзита.
- По мере удаления от марта 2026 года полнота публикации может значительно снижаться.''')
