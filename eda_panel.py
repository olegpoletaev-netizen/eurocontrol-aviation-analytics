"""EDA dashboard for the existing read-only EUROCONTROL airport-day panel.

No I/O, SQL mutations or external calls: receives the already filtered DataFrame
from app.py.  Statistical flags are descriptive, not verified real-world events.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
FEATURES = [
    ('airport_icao', 'Категориальный', 'Код аэропорта ICAO; идентификатор аэропорта'),
    ('airport_name', 'Категориальный', 'Человекочитаемое название аэропорта'),
    ('date', 'Дата', 'Дата отдельного календарного дня'),
    ('year', 'Календарный', 'Год наблюдения, производный от даты'),
    ('month', 'Календарный', 'Номер месяца, производный от даты'),
    ('weekday', 'Календарный', 'День недели (0 = понедельник), производный от даты'),
    ('traffic_total_dy', 'Числовой', 'Суточные авиадвижения (прилёты + вылеты); NULL означает отсутствие данных'),
    ('data_status', 'Категориальный', 'Статус получения суточной метрики'),
]


def prepare_eda(frame: pd.DataFrame) -> pd.DataFrame:
    required = {'date', 'airport_icao', 'traffic_total_dy', 'data_status', 'airport_name'}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'Для EDA не хватает колонок: {sorted(missing)}')
    d = frame.copy()
    d['date'] = pd.to_datetime(d['date'])
    d['traffic_total_dy'] = pd.to_numeric(d['traffic_total_dy'], errors='coerce')
    d['year'] = d['date'].dt.year
    d['month'] = d['date'].dt.month
    d['weekday'] = d['date'].dt.dayofweek
    d['weekday_ru'] = d['weekday'].map(dict(enumerate(WEEKDAYS)))
    d['month_date'] = d['date'].dt.to_period('M').dt.to_timestamp()
    return d


def describe_airports(d):
    g = d.groupby('airport_icao', as_index=False).agg(
        days=('date', 'size'), observed=('traffic_total_dy', 'count'),
        mean_daily=('traffic_total_dy', 'mean'),
        median_daily=('traffic_total_dy', 'median'),
        std_daily=('traffic_total_dy', 'std'),
        min_daily=('traffic_total_dy', 'min'), max_daily=('traffic_total_dy', 'max'))
    g['missing'] = g['days'] - g['observed']
    g['coverage_pct'] = np.where(g['days'] > 0, g['observed'] / g['days'] * 100, np.nan)
    g['cv_pct'] = np.where(g['mean_daily'] > 0, 100 * g['std_daily'] / g['mean_daily'], np.nan)
    return g


def detect_anomalies(d, cutoff=3.5, min_baseline=8):
    """Per-airport, per-weekday leave-in robust z score; no zero filling.

    A zero MAD produces no anomaly label, rather than a false infinite score.
    """
    x = d.copy()
    grp = ['airport_icao', 'weekday']
    x['weekday_baseline_n'] = x.groupby(grp)['traffic_total_dy'].transform('count')
    x['weekday_baseline_median'] = x.groupby(grp)['traffic_total_dy'].transform('median')
    x['abs_dev'] = (x['traffic_total_dy'] - x['weekday_baseline_median']).abs()
    x['weekday_mad'] = x.groupby(grp)['abs_dev'].transform('median')
    ok = x['traffic_total_dy'].notna() & x['weekday_baseline_n'].ge(min_baseline) & x['weekday_mad'].gt(0)
    x['robust_z'] = np.nan
    x.loc[ok, 'robust_z'] = (0.67448975 * (x.loc[ok, 'traffic_total_dy'] - x.loc[ok, 'weekday_baseline_median']) / x.loc[ok, 'weekday_mad'])
    x['is_anomaly'] = x['robust_z'].abs().ge(cutoff) & x['robust_z'].notna()
    return x


def monthly_stats(d):
    g = d.groupby(['airport_icao', 'month_date'], as_index=False).agg(
        observed_days=('traffic_total_dy', 'count'),
        calendar_rows=('date', 'size'),
        mean_daily=('traffic_total_dy', 'mean'))
    g['missing_days'] = g['calendar_rows'] - g['observed_days']
    g['coverage_pct'] = 100 * g['observed_days'] / g['calendar_rows']
    return g


def render_eda_panel(frame: pd.DataFrame):
    st.subheader('Разведочный анализ (EDA) · EUROCONTROL')
    st.caption('Единица наблюдения — аэропорт × календарная дата. Анализ использует выбранные в боковой панели аэропорты и даты; только локальная DuckDB, никаких внешних запросов.')
    if frame.empty:
        st.info('Нет записей для выбранных аэропортов и дат.')
        return
    d = prepare_eda(frame)
    q = describe_airports(d)
    m = monthly_stats(d)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Аэропортов', d['airport_icao'].nunique())
    c2.metric('Строк «аэропорт × день»', f'{len(d):,}'.replace(',', ' '))
    c3.metric('Числовых наблюдений', f'{d.traffic_total_dy.count():,}'.replace(',', ' '))
    c4.metric('Пропущенных значений', f'{d.traffic_total_dy.isna().sum():,}'.replace(',', ' '))
    with st.expander('Объекты и признаки: описание аналитической таблицы', expanded=True):
        st.dataframe(pd.DataFrame(FEATURES, columns=['Признак', 'Тип', 'Описание']), hide_index=True, use_container_width=True)
        st.caption('Поля year, month, weekday, month_date вычисляются из date для EDA. Структура исходной базы не меняется.')
        st.dataframe(d[['airport_icao', 'airport_name', 'date', 'traffic_total_dy', 'data_status']].head(20), hide_index=True, use_container_width=True)
        st.download_button('Скачать выбранные объекты–признаки (CSV)', d[['airport_icao','airport_name','date','year','month','weekday','traffic_total_dy','data_status']].to_csv(index=False).encode('utf-8-sig'), file_name='eda_airport_day_features.csv', mime='text/csv')
    st.markdown('### Описательная статистика')
    display = q.rename(columns={'airport_icao':'ICAO','days':'Календарных строк','observed':'Наблюдений','missing':'Пропусков','coverage_pct':'Покрытие, %','mean_daily':'Среднее/день','median_daily':'Медиана/день','std_daily':'Ст. отклонение','cv_pct':'CV, %','min_daily':'Минимум','max_daily':'Максимум'})
    st.dataframe(display.round(2), use_container_width=True, hide_index=True)
    st.download_button('Скачать EDA-статистику', q.to_csv(index=False).encode('utf-8-sig'),file_name='eda_summary.csv',mime='text/csv')
    st.markdown('### Распределение суточного трафика')
    view = d.dropna(subset=['traffic_total_dy'])
    if not view.empty:
        scale = st.radio('Масштаб', ['Абсолютные авиадвижения', 'Отношение к медиане аэропорта'], horizontal=True, key='eda_scale')
        sample = view.copy()
        if scale == 'Отношение к медиане аэропорта':
            med = sample.groupby('airport_icao')['traffic_total_dy'].transform('median')
            sample['plot_value'] = sample['traffic_total_dy'].div(med.where(med.gt(0)))
            axis_label = 'Трафик / медиана аэропорта'
        else:
            sample['plot_value'] = sample['traffic_total_dy']
            axis_label = 'Авиадвижения в сутки'
        fig = px.histogram(sample, x='plot_value', color='airport_icao', barmode='overlay', nbins=45,
                           labels={'plot_value':axis_label,'airport_icao':'ICAO'}, title='Распределение наблюдаемых значений')
        st.plotly_chart(fig, use_container_width=True)
        st.caption('Различие в масштабе аэропортов может скрывать форму распределения; режим нормирования показывает относительные значения. Пропуски исключены, не приравнены к нулю.')
    st.markdown('### Календарная сезонность')
    col_a, col_b = st.columns(2)
    observed = d.dropna(subset=['traffic_total_dy'])
    if not observed.empty:
        weekday = observed.groupby('weekday', as_index=False).agg(mean_daily=('traffic_total_dy','mean'),n=('traffic_total_dy','size'))
        weekday['День'] = weekday['weekday'].map(dict(enumerate(WEEKDAYS)))
        with col_a:
            st.plotly_chart(px.bar(weekday, x='День', y='mean_daily', labels={'mean_daily':'Среднее авиадвижений / аэропорт-день'}, title='День недели'), use_container_width=True)
        mon = observed.groupby('month', as_index=False).agg(mean_daily=('traffic_total_dy','mean'),n=('traffic_total_dy','size'))
        mon['Месяц'] = mon['month'].map({i+1: x for i,x in enumerate(MONTHS)})
        with col_b:
            st.plotly_chart(px.line(mon, x='Месяц', y='mean_daily', markers=True, labels={'mean_daily':'Среднее авиадвижений / аэропорт-день'}, title='Месяц года', category_orders={'Месяц':MONTHS}),use_container_width=True)
        st.caption('Средние отражают состав выбранных аэропортов и фактически доступные годы; неполный 2026 год и несбалансированные периоды могут менять профиль сезонности.')
    st.markdown('### Тепловая карта: аэропорт × месяц')
    if not m.empty:
        metric = st.selectbox('Показатель тепловой карты', ['Среднее число авиадвижений в наблюдаемый день','Покрытие данных, %'], key='eda_heatmap_metric')
        key = 'mean_daily' if metric.startswith('Среднее') else 'coverage_pct'
        wide = m.pivot(index='airport_icao', columns='month_date', values=key)
        fig = px.imshow(wide, aspect='auto', color_continuous_scale='Viridis', labels={'x':'Месяц','y':'Аэропорт','color':metric}, title=metric)
        st.plotly_chart(fig,use_container_width=True)
        st.caption('Среднее за наблюдаемые дни, а не месячная сумма; для неполных месяцев отдельно проверяйте покрытие. Месяцы за пределами выбранного диапазона не включаются.')
    st.markdown('### Статистические аномалии')
    threshold = st.slider('Порог абсолютного robust z (MAD)', 2.5, 8.0, 3.5, 0.5, key='eda_anomaly_threshold')
    flagged = detect_anomalies(d, cutoff=threshold)
    anomalies = flagged[flagged['is_anomaly']].copy().sort_values('robust_z')
    total_evaluable = flagged['robust_z'].notna().sum()
    a,b = st.columns(2)
    a.metric('Статистических выбросов', int(len(anomalies)))
    b.metric('Дней с вычислимой диагностикой', int(total_evaluable))
    if not anomalies.empty:
        codes = anomalies['airport_icao'].unique().tolist()
        code = st.selectbox('Аэропорт на графике аномалий', codes, key='eda_anomaly_airport')
        series = flagged[(flagged['airport_icao'] == code) & flagged['traffic_total_dy'].notna()]
        fig = px.line(series, x='date', y='traffic_total_dy', labels={'date':'Дата','traffic_total_dy':'Авиадвижения'},title=f'{code}: дневной трафик и статистические выбросы')
        points = anomalies[anomalies['airport_icao'] == code]
        fig.add_scatter(x=points['date'], y=points['traffic_total_dy'], mode='markers', name='Статистический выброс',marker={'size':10,'color':'crimson'})
        st.plotly_chart(fig,use_container_width=True)
        cols = ['airport_icao','date','traffic_total_dy','weekday_baseline_median','weekday_baseline_n','robust_z']
        st.dataframe(anomalies[cols].rename(columns={'airport_icao':'ICAO','date':'Дата','traffic_total_dy':'Авиадвижения','weekday_baseline_median':'Медиана соответствующего дня недели','weekday_baseline_n':'Число базовых наблюдений','robust_z':'Robust z'}).round(2), hide_index=True,use_container_width=True)
    else:
        st.info('При выбранных фильтрах и пороге аномалии не найдены. Это не означает отсутствия операционных инцидентов.')
    st.download_button('Скачать выявленные статистические выбросы', anomalies[['airport_icao','date','traffic_total_dy','robust_z']].to_csv(index=False).encode('utf-8-sig'),file_name='eda_anomalies.csv',mime='text/csv')
    st.caption('Метод: медиана и MAD отдельно по аэропорту и дню недели в выбранном диапазоне, минимум 8 наблюдений, |0.67449 × (x − медиана)/MAD| ≥ порога. Если MAD=0, оценка не вычисляется. Флаги НЕ подтверждают причины и не являются установленными авиационными событиями; изменение периода меняет базовый уровень.')
