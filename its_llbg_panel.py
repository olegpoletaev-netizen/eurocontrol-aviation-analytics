"""ITS LLBG: descriptive model results from vetted exported CSVs; no database writes."""
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

@st.cache_data
def load_its(folder):
    folder=Path(folder)
    data={}
    for name in ("its_llbg_daily", "its_llbg_windows", "its_llbg_diagnostics", "its_llbg_placebo"):
        data[name]=pd.read_csv(folder / (name+".csv"))
    return data

def render_its_panel(folder):
    st.subheader("Interrupted Time Series · LLBG (Тель-Авив)")
    st.caption("Дата кризиса: 28.02.2026 · Дневной трафик EUROCONTROL · прогноз только по докризисным данным")
    if any(not (Path(folder)/(name+".csv")).exists() for name in ("its_llbg_daily", "its_llbg_windows", "its_llbg_diagnostics", "its_llbg_placebo")):
        st.warning("Не найдены выгрузки ITS в папке its_llbg_data/. Проверьте установку комплекта.")
        return
    d=load_its(str(folder)); daily=d['its_llbg_daily'].copy(); windows=d['its_llbg_windows'].copy()
    daily['date']=pd.to_datetime(daily['date'])
    primary=windows[windows['scenario'].eq('full_pre_only')]
    head=primary[primary['window'].eq('D01_28')]
    if not head.empty:
        h=head.iloc[0]; a,b,c=st.columns(3)
        a.metric('Фактические операции, 28 дней', f"{h['actual_total']:,.0f}".replace(',', ' '))
        b.metric('Прогноз операций, 28 дней', f"{h['expected_total']:,.0f}".replace(',', ' '))
        c.metric('Отклонение от прогноза',f"{h['difference_pct']:.1f}%")
    options={'Дни 1–28':('D01_28',1,28),'Дни 29–56':('D29_56',29,56),'Дни 57–90':('D57_90',57,90),'Все 90 дней':('ALL',1,90)}
    choice=st.radio('Период на графике', list(options), index=3, horizontal=True, key='its_period')
    _,first_day,last_day=options[choice]
    daily=daily.iloc[first_day-1:last_day].copy()
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=daily['date'], y=daily['actual'], name='Фактически', mode='lines'))
    fig.add_trace(go.Scatter(x=daily['date'], y=daily['expected'], name='Прогноз ITS', mode='lines'))
    fig.add_trace(go.Scatter(x=daily['date'], y=daily['upper_pointwise_95'], mode='lines',line=dict(width=0),hoverinfo='skip',showlegend=False))
    fig.add_trace(go.Scatter(x=daily['date'], y=daily['lower_pointwise_95'], mode='lines',fill='tonexty',fillcolor='rgba(110,120,150,0.18)',line=dict(width=0), name='Модельный интервал (по дням)'))
    fig.update_layout(xaxis_title='Дата',yaxis_title='Операции в сутки',height=420,legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Границы показаны для отдельных дней; это не причинные доверительные интервалы. Прогнозные оценки чувствительны к спецификации модели.')
    st.markdown('**Отклонения по неперекрывающимся периодам**')
    sub=primary[primary['window'].isin(['D01_28','D29_56','D57_90'])].copy()
    sub['Период']=sub['window'].map({'D01_28':'Дни 1–28','D29_56':'Дни 29–56','D57_90':'Дни 57–90'})
    display=sub[['Период','actual_total','expected_total','difference_pct','model_uncertainty_pct_low_95','model_uncertainty_pct_high_95']].rename(columns={
        'actual_total':'Фактически','expected_total':'Прогноз','difference_pct':'Отклонение, %',
        'model_uncertainty_pct_low_95':'Нижняя оценка, %','model_uncertainty_pct_high_95':'Верхняя оценка, %'})
    display['Фактически']=display['Фактически'].round(0).astype(int)
    st.dataframe(display,hide_index=True,use_container_width=True,column_config={
        'Прогноз':st.column_config.NumberColumn(format='%.0f'),
        'Отклонение, %':st.column_config.NumberColumn(format='%.1f%%'),
        'Нижняя оценка, %':st.column_config.NumberColumn(format='%.1f%%'),
        'Верхняя оценка, %':st.column_config.NumberColumn(format='%.1f%%')})
    with st.expander('Чувствительность, placebo и диагностика'):
        st.markdown('**Альтернативные обучающие окна**')
        st.dataframe(windows[windows['window'].eq('D01_28')][['scenario','actual_total','expected_total','difference_pct']],hide_index=True,use_container_width=True)
        st.markdown('**Диагностика остатков**')
        st.dataframe(d['its_llbg_diagnostics'][['scenario','pre_residual_lag1_autocorr','residual_ljungbox_lag14_p','pre_log_rmse']],hide_index=True,use_container_width=True)
        st.markdown('**Псевдособытие 28.02.2025**')
        st.dataframe(d['its_llbg_placebo'][['window','difference_pct','actual_total','expected_total']],hide_index=True,use_container_width=True)
    st.warning('Важно: лаговая автокорреляция основной модели ≈0,841; placebo 2025 обнаруживает существенные отклонения. ITS здесь — описательное отличие от модельного ориентира, НЕ доказанный причинный эффект конфликта.')
    st.download_button('Скачать полный дневной ряд ITS (CSV)',d['its_llbg_daily'].to_csv(index=False).encode('utf-8-sig'),file_name='its_llbg_daily.csv',mime='text/csv')

    st.divider()
    from its_validation_panel import render_validation
    render_validation(Path(folder).parent / 'its_validation_data')
