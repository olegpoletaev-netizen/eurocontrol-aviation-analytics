"""Streamlit model comparison panel. Displays only computed and auditable CSVs."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

NAMES={'ols_fourier':'OLS + Fourier (statsmodels)',
       'glsar_ar1':'GLSAR AR(1) (statsmodels)',
       'seasonal_naive_364':'Прошлый год −364 дня (pandas)',
       'sklearn_hist_gradient_boosting':'HistGradientBoosting (scikit-learn)'}
WINDOWS={'D01_28':'Первые 28 дней','CUM_01_56':'Первые 56 дней','CUM_01_90':'Все 90 дней'}
@st.cache_data(show_spinner=False)
def load_folder(folder):
    p=Path(folder)
    return tuple(pd.read_csv(p/name,encoding='utf-8-sig') for name in
      ('model_comparison_summary.csv','model_comparison_backtests.csv','model_comparison_post.csv'))

def render_model_comparison(folder):
    p=Path(folder)
    required=('model_comparison_summary.csv','model_comparison_backtests.csv','model_comparison_post.csv')
    st.markdown('### Сравнение моделей: статистика и машинное обучение')
    st.caption('statsmodels · scikit-learn · pandas. Семь одинаковых докризисных точек проверки в 2025 году; прогноз строго из прошлого.')
    if not all((p/name).exists() for name in required):
        st.info('Сначала запустите model_comparison_v1/run_model_comparison.py и скопируйте его results в model_comparison_data. Без расчёта результаты не подставляются.')
        return
    summary,bt,post=load_folder(str(p))
    horizon=st.selectbox('Горизонт сравнения',list(WINDOWS),format_func=lambda x:WINDOWS[x],key='mc_horizon')
    ss=summary[summary.window==horizon].copy()
    ss['Модель']=ss.model.map(NAMES)
    ss=ss.sort_values('median_abs_pct_error')
    if ss.empty:
        st.warning('Нет данных для этого горизонта.')
        return
    st.success(f"Минимальная медианная ошибка суммы на исторических периодах: {ss.iloc[0]['Модель']} — {ss.iloc[0]['median_abs_pct_error']:.2f}%")
    vis=ss[['Модель','median_abs_pct_error']].rename(columns={'median_abs_pct_error':'Медианная ошибка, %'})
    st.plotly_chart(px.bar(vis,x='Модель',y='Медианная ошибка, %',title='Историческая точность прогноза (меньше — лучше)'),use_container_width=True)
    show=ss[['Модель','origins','median_abs_pct_error','mean_daily_mae','mean_daily_rmse']].rename(columns={
      'origins':'Тестовых дат','median_abs_pct_error':'Медианная ошибка суммы, %',
      'mean_daily_mae':'Средняя MAE в сутки','mean_daily_rmse':'Средняя RMSE в сутки'})
    st.dataframe(show,hide_index=True,use_container_width=True)
    st.markdown('**Наблюдаемое падение LLBG после 28.02.2026 — разные прогнозные ориентиры**')
    pp=post[post.window==horizon].copy()
    pp['Модель']=pp.model.map(NAMES)
    st.dataframe(pp[['Модель','actual_total','forecast_total','error_pct']].rename(columns={
      'actual_total':'Фактически','forecast_total':'Прогноз','error_pct':'Отклонение, %'}),
      hide_index=True,use_container_width=True)
    with st.expander('Проверяемость и ограничения'):
        st.warning('Сравнение прогнозов не доказывает причинность. Исторические окна перекрываются, 2025 год включал независимые шоки, а HGB может плохо экстраполировать тренд. MAPE при нулевом факте не определён: оцениваем ошибку суммы за окно и дневные MAE/RMSE.')
        st.download_button('Скачать сравнение (CSV)',summary.to_csv(index=False).encode('utf-8-sig'),file_name='model_comparison_summary.csv',mime='text/csv',key='mc_download')
