"""EUROCONTROL Aviation Analytics – local Windows Streamlit application."""
from pathlib import Path
import datetime as dt
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EUROCONTROL · Aviation Analytics", page_icon="✈️", layout="wide")
ROOT = Path(__file__).resolve().parent
DB = ROOT / "aviation_analytics.duckdb"
if not DB.exists():
    st.error("Не найдена aviation_analytics.duckdb рядом с app.py. Для облачной публикации добавьте разрешённую к распространению копию базы в корень репозитория. Подробности в CLOUD_DEPLOY_README_RU.md.")
    st.stop()

@st.cache_resource
def db_connection(path, modified):
    return duckdb.connect(str(path), read_only=True)

conn = db_connection(DB, DB.stat().st_mtime)

@st.cache_data(ttl=120)
def query(sql, params=()):
    return conn.execute(sql, list(params)).df()

meta = query("SELECT min(date) min_date, max(date) max_date, count(*) n FROM fact_airport_daily")
first = meta.iloc[0]["min_date"]
last = meta.iloc[0]["max_date"]
first = pd.Timestamp(first).date()
last = pd.Timestamp(last).date()
airports = query("SELECT airport_id, airport_icao, airport_name FROM dim_airport ORDER BY airport_icao")
labels = {f"{r.airport_icao} — {r.airport_name or ''}": int(r.airport_id) for r in airports.itertuples()}

st.title("✈️ EUROCONTROL · Aviation Analytics")
st.caption("Аналитика авиадвижений 113 аэропортов · 2024–2026 · DuckDB (только чтение)")
with st.sidebar:
    st.header("Фильтры")
    selection = st.multiselect("Аэропорты", options=list(labels), default=list(labels)[:5], help="Выберите аэропорты для построения графиков и сравнений")
    ids = [labels[x] for x in selection]
    st.caption(f"Выбрано: {len(ids)} из {len(labels)}")
    start = st.date_input("Начало периода (ДД/ММ/ГГГГ)", value=first, min_value=first, max_value=last, format="DD/MM/YYYY")
    finish = st.date_input("Окончание периода (ДД/ММ/ГГГГ)", value=last, min_value=first, max_value=last, format="DD/MM/YYYY")
    st.markdown("---")
    st.caption("TrafficTotalDY — количество авиадвижений в аэропорту (прилёты + вылеты), не уникальные сетевые рейсы.")
if not ids:
    st.info("Выберите хотя бы один аэропорт.")
    st.stop()
if start > finish:
    st.error("Начало периода позднее окончания.")
    st.stop()

marks = ",".join("?" for _ in ids)
data = query(f"""
    SELECT v.date, v.year, v.month, v.airport_icao, v.airport_name,
           v.traffic_total_dy, v.data_status
    FROM vw_airport_daily v
    WHERE v.airport_id IN ({marks}) AND v.date BETWEEN ? AND ?
    ORDER BY v.date, v.airport_icao
""", (*ids, start, finish))
data["date"] = pd.to_datetime(data["date"])
data["year"] = data["year"].astype(int)
valid = data.dropna(subset=["traffic_total_dy"])

section_overview, section_eda, section_compare, section_olap, section_quality, section_routes, section_its, section_events, section_method = st.tabs([
    "Обзор", "Разведочный анализ (EDA)", "Сравнение годов", "OLAP-анализ", "Качество данных", "Международные направления", "ITS · LLBG", "События 2024–2026", "Методология"
])

with section_overview:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Авиадвижения", f"{valid.traffic_total_dy.sum():,.0f}".replace(",", " "))
    c2.metric("Аэропортов", data.airport_icao.nunique())
    c3.metric("Дней с наблюдением", valid.date.nunique())
    c4.metric("Пропусков", int(data.traffic_total_dy.isna().sum()))
    interval = st.radio("Шаг графика", ["День", "Месяц"], index=1, horizontal=True)
    chart = valid.copy()
    chart["period"] = chart.date if interval == "День" else chart.date.dt.to_period("M").dt.to_timestamp()
    chart = chart.groupby(["period", "airport_icao"], as_index=False)["traffic_total_dy"].sum()
    st.plotly_chart(px.line(chart, x="period", y="traffic_total_dy", color="airport_icao", labels={"traffic_total_dy":"Авиадвижения", "period":"Дата", "airport_icao":"ICAO"}), use_container_width=True)
    st.caption("Месячная сумма может быть неполной при наличии пропусков; см. вкладку «Качество данных».")

with section_eda:
    from eda_panel import render_eda_panel
    render_eda_panel(data)

with section_compare:
    st.subheader("Сравнение годов на одинаковом интервале")
    left,right,third = st.columns(3)
    year_base = left.selectbox("Базовый год", [2024,2025,2026], index=0)
    year_compare = right.selectbox("Сравниваемый год", [2024,2025,2026], index=1)
    mode = third.selectbox("Период", ["Январь — сентябрь", "Полный год (если доступен)", "Выбрать месяцы"], index=0)
    if mode == "Выбрать месяцы":
        month_start,month_end = st.select_slider("Месяцы", options=list(range(1,13)), value=(1,9))
    elif mode == "Январь — сентябрь":
        month_start,month_end=1,9
    else:
        month_start,month_end=1,12
    if year_base == year_compare:
        st.info("Выберите два разных года.")
    else:
        # Exact matching month/day pairs prevents leap-day distortion and compares equal calendar windows.
        yr_data=query(f"""SELECT v.date,v.year,v.month,v.airport_icao,v.traffic_total_dy
              FROM vw_airport_daily v WHERE v.airport_id IN ({marks})
              AND v.year IN (?,?) AND v.month BETWEEN ? AND ?
              ORDER BY v.airport_icao, v.date""", (*ids,year_base,year_compare,month_start,month_end))
        yr_data['date']=pd.to_datetime(yr_data['date'])
        yr_data['day_key']=yr_data['date'].dt.strftime('%m-%d')
        # Restrict to calendar days existing in both years for each airport.
        a=yr_data[yr_data.year==year_base].set_index(['airport_icao','day_key'])
        b=yr_data[yr_data.year==year_compare].set_index(['airport_icao','day_key'])
        merged=a[['traffic_total_dy']].join(b[['traffic_total_dy']],how='inner',lsuffix='_base',rsuffix='_cmp')
        summary=[]
        for code,g in merged.groupby(level=0):
            base_missing=int(g.traffic_total_dy_base.isna().sum())
            cmp_missing=int(g.traffic_total_dy_cmp.isna().sum())
            observed=g.dropna(subset=['traffic_total_dy_base','traffic_total_dy_cmp'])
            n=int(len(observed))
            x=float(observed.traffic_total_dy_base.sum())
            y=float(observed.traffic_total_dy_cmp.sum())
            pct=100*(y/x-1) if n and x>0 else None
            summary.append({'ICAO':code,'Сопоставимых дней':n,'Пропусков (база)':base_missing,
             'Пропусков (сравнение)':cmp_missing,'База, движения':int(x),
             'Сравнение, движения':int(y),'Изменение, %':pct,
             'Полный период':base_missing==0 and cmp_missing==0})
        result=pd.DataFrame(summary)
        st.dataframe(result,hide_index=True,use_container_width=True)
        if not result.empty:
            fig=px.bar(result,x='ICAO',y='Изменение, %',title='Изменение по совпадающим наблюдаемым датам')
            st.plotly_chart(fig,use_container_width=True)
        st.warning("Сопоставление ведётся по одинаковым календарным датам, присутствующим в обоих годах. Если есть пропуски, % рассчитывается только по парным наблюдениям. Не интерпретируйте его как изменение полного календарного периода. Для 2026 года данные доступны лишь по 30.09.2026; 29 февраля 2024 не включается, если в другом году его нет.")

with section_olap:
    st.subheader("OLAP: группировки и сводные таблицы")
    granularity=st.selectbox('Измерение времени',["Год", "Квартал", "Месяц", "Дата"],index=2)
    cols={'Год':['year'],'Квартал':['year','quarter'],'Месяц':['year','month'],'Дата':['date']}[granularity]
    dims=st.multiselect('Дополнительные измерения',['airport_icao','airport_name'],default=['airport_icao'])
    allcols=cols+dims
    allowed={'year','quarter','month','date','airport_icao','airport_name'}
    assert set(allcols)<=allowed
    select=', '.join(allcols)
    rows=query(f"""SELECT {select}, SUM(traffic_total_dy) AS movements,
       COUNT(traffic_total_dy) AS observed_days, COUNT(*) AS expected_days,
       COUNT(*) - COUNT(traffic_total_dy) AS missing_days
       FROM vw_airport_daily
       WHERE airport_id IN ({marks}) AND date BETWEEN ? AND ?
       GROUP BY {select} ORDER BY {select}""",(*ids,start,finish))
    rows['complete']=rows['missing_days'].eq(0)
    st.dataframe(rows,use_container_width=True,hide_index=True)
    st.download_button('Скачать OLAP CSV',rows.to_csv(index=False).encode('utf-8-sig'),
                       file_name='eurocontrol_olap.csv',mime='text/csv')
    st.caption("SUM игнорирует NULL; пропуски отображаются отдельно. Для неполных периодов сравнение абсолютных сумм требует осторожности.")

with section_quality:
    st.subheader("Все известные пропуски TrafficTotalDY")
    st.markdown("**37 подтверждённых отсутствий метрики за 2024–2026 годы.** NO_DY означает, что API не предоставил суточное значение; это **не** доказательство отсутствия авиадвижений. Значения хранятся как `NULL`, а не `0`.")
    quality=query("""SELECT f.date,a.airport_icao,a.airport_name,q.quality_code,q.description
         FROM fact_data_quality q JOIN dim_airport a USING (airport_id)
         JOIN fact_airport_daily f ON f.airport_id=q.airport_id AND f.date=q.date
         ORDER BY f.date,a.airport_icao""")
    st.metric('Пропуски во всей базе',len(quality))
    st.dataframe(quality,hide_index=True,use_container_width=True)
    st.download_button('Скачать 37 пропусков CSV', quality.to_csv(index=False).encode('utf-8-sig'),
                       file_name='eurocontrol_missing_37.csv',mime='text/csv')
    st.subheader("Покрытие данных по аэропорту и году")
    coverage=query("""SELECT airport_icao,year,COUNT(*) expected_days,COUNT(traffic_total_dy) observed_days,
          COUNT(*)-COUNT(traffic_total_dy) missing_days,
          ROUND(100.0*COUNT(traffic_total_dy)/COUNT(*),3) coverage_pct
          FROM vw_airport_daily GROUP BY ALL ORDER BY airport_icao,year""")
    st.dataframe(coverage,hide_index=True,use_container_width=True)
    st.download_button('Скачать покрытие CSV', coverage.to_csv(index=False).encode('utf-8-sig'),
                       file_name='eurocontrol_coverage.csv',mime='text/csv')

with section_routes:
    from eurostat_route_analytics_v1.route_streamlit_panel import render_route_panel
    render_route_panel(ROOT / "eurostat_route_analytics_v1" / "data")


with section_its:
    from its_llbg_panel import render_its_panel
    render_its_panel(ROOT / "its_llbg_data")
    from model_comparison_panel import render_model_comparison
    render_model_comparison(ROOT / "model_comparison_data")

with section_events:
    from event_registry.events_panel import render_events_panel
    render_events_panel(ROOT / "event_registry")

with section_method:
    st.markdown("""### Определения и ограничения
- **Источник:** EUROCONTROL Data App API, `networkType=total`, `dateRange=DY`.
- **TrafficTotalDY:** авиадвижения в аэропорту; это не число уникальных авиарейсов всей сети.
- **NO_DY:** дневное значение не удалось получить, в том числе после адресной проверки 28 отсутствующих дней 2024 года.
- **NO_DY_OR_MISSING:** для 2025–2026 годов отдельный статус исходного объединённого набора; нельзя интерпретировать как ноль.
- **2024 и 2025:** полные календарные годы в смысле охвата дат, но не каждый аэропорт имеет числовое значение каждый день.
- **2026:** данные по 30 сентября. Для корректного YoY используйте совпадающие даты, а пропуски показывайте отдельно.
- **Межгодовое сравнение:** сравнение суммарных авиадвижений по двум одинаковым наборам наблюдаемых календарных дат; при пропусках результаты относятся только к сопоставленным датам.
- **Причины пропусков:** статус API сам по себе не устанавливает причину; закрытия аэропортов и забастовки требуют внешнего подтверждения.
- **Ограничение исследования:** выборка 113 аэропортов не представляет собой весь авиационный трафик Европы.
""")
