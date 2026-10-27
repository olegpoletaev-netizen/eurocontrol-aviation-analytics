"""ITS Validation v2: seven historical backtests and three forecast specifications."""
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

MODELS = {'ols_fourier':'OLS + Fourier (основная)', 'glsar_ar1':'GLSAR AR(1)', 'seasonal_naive_364':'Сезонный ориентир −364 дня'}
WINDOWS = {'D01_28':'Дни 1–28', 'D29_56':'Дни 29–56', 'D57_90':'Дни 57–90', 'CUM_01_28':'Накопленные 28 дней', 'CUM_01_56':'Накопленные 56 дней', 'CUM_01_90':'Накопленные 90 дней'}
FILES = ('backtest_model_summary','backtest_origin_windows','historical_error_calibration','post_daily_validation','post_model_comparison')

@st.cache_data(show_spinner=False)
def load_validation(path):
    root=Path(path)
    return {name:pd.read_csv(root/(name+'.csv'),encoding='utf-8-sig') for name in FILES}

def render_validation(path):
    root=Path(path)
    if not all((root/(name+'.csv')).is_file() for name in FILES):
        st.warning('Нет файлов ITS Validation v2. Проверьте папку its_validation_data.')
        return
    tab=load_validation(str(root))
    post=tab['post_model_comparison'].copy()
    back=tab['backtest_model_summary'].copy()
    calibration=tab['historical_error_calibration'].copy()
    origins=tab['backtest_origin_windows'].copy()
    daily=tab['post_daily_validation'].copy()
    st.markdown('### ITS Validation v2 · историческая проверка прогноза')
    st.caption('7 исторических дат 2025 года · 3 модели · одинаковые горизонты 28/56/90 дней. Это анализ качества прогнозного ориентира, а не причинная идентификация.')
    opts=list(MODELS)
    selected=st.selectbox('Модель для сравнения с фактом',opts,format_func=lambda x:MODELS[x],key='validation_model')
    window=st.selectbox('Период анализа', ['D01_28','D29_56','D57_90','CUM_01_90'],format_func=lambda x:WINDOWS[x],key='validation_window')
    one=post[(post.model==selected)&(post.window==window)]
    if not one.empty:
        r=one.iloc[0]
        a,b,c=st.columns(3)
        a.metric('Фактически',f"{r['actual_total']:,.0f}".replace(',',' '))
        b.metric('Прогноз модели',f"{r['forecast_total']:,.0f}".replace(',',' '))
        c.metric('Отклонение от прогноза',f"{r['error_pct']:.1f}%")
    start_end={'D01_28':(1,28),'D29_56':(29,56),'D57_90':(57,90),'CUM_01_90':(1,90)}
    d1,d2=start_end[window]
    view=daily[(daily.model==selected)&daily.day.between(d1,d2)].copy()
    view['date']=pd.to_datetime(view['date'])
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=view.date,y=view.actual,name='Фактические операции',mode='lines'))
    fig.add_trace(go.Scatter(x=view.date,y=view.predicted,name='Прогноз выбранной модели',mode='lines'))
    fig.update_layout(height=365,xaxis_title='Дата',yaxis_title='Операции в сутки',legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Интервалы ITS v1 на этом сравнительном графике не показаны: для GLSAR и сезонного ориентира идентичные прогнозные интервалы не рассчитывались.')
    st.markdown('**Сопоставление трёх моделей по выбранному периоду**')
    compare=post[post.window==window][['model','actual_total','forecast_total','error_pct']].copy()
    compare['model']=compare['model'].map(MODELS)
    compare=compare.rename(columns={'model':'Модель','actual_total':'Фактически','forecast_total':'Прогноз','error_pct':'Отклонение, %'})
    st.dataframe(compare,hide_index=True,use_container_width=True,column_config={'Фактически':st.column_config.NumberColumn(format='%.0f'),'Прогноз':st.column_config.NumberColumn(format='%.0f'),'Отклонение, %':st.column_config.NumberColumn(format='%.1f%%')})
    st.markdown('**Точность на исторических датах (медианная абсолютная ошибка суммы, %)**')
    metric_windows=['D01_28','CUM_01_56','CUM_01_90']
    perf=back[back.window.isin(metric_windows)][['model','window','median_abs_pct_error','origins']].copy()
    perf['Модель']=perf.model.map(MODELS)
    perf['Горизонт']=perf.window.map(WINDOWS)
    perf=perf.rename(columns={'median_abs_pct_error':'Медианная абсолютная ошибка, %','origins':'Исторических дат'})
    st.dataframe(perf[['Модель','Горизонт','Медианная абсолютная ошибка, %','Исторических дат']],hide_index=True,use_container_width=True,column_config={'Медианная абсолютная ошибка, %':st.column_config.NumberColumn(format='%.2f%%')})
    c=calibration[(calibration.model==selected)&(calibration.window==window)]
    if not c.empty:
        t=c.iloc[0]
        message=('Выходит за исторический диапазон' if bool(t.post_outside_historical_range) else 'Находится внутри исторического диапазона')
        st.info(f"Сравнение с семью историческими окнами: {message}. Исторические отклонения: {t.historical_min_error_pct:.1f}% … {t.historical_max_error_pct:.1f}%.")
    with st.expander('Детали backtesting, ограничения и экспорт'):
        org=origins[(origins.model==selected)&(origins.window==window)][['origin','actual_total','forecast_total','error_pct']].copy()
        st.dataframe(org.rename(columns={'origin':'Дата начала теста','actual_total':'Фактически','forecast_total':'Прогноз','error_pct':'Отклонение, %'}),hide_index=True,use_container_width=True)
        st.download_button('Скачать исторические проверки (CSV)',origins.to_csv(index=False).encode('utf-8-sig'),file_name='its_v2_backtest_origin_windows.csv',mime='text/csv',key='its_v2_backtest_download')
        st.download_button('Скачать прогнозы моделей (CSV)',daily.to_csv(index=False).encode('utf-8-sig'),file_name='its_v2_post_daily_validation.csv',mime='text/csv',key='its_v2_daily_download')
        st.markdown('**Ограничения:** семь исторических дат не являются независимой большой выборкой; горизонты частично перекрываются. Историческое отклонение не является p-value. OLS и GLSAR оставляют выраженную остаточную автокорреляцию. Сезонный ориентир — сравнение с соответствующими днями недели 2025 года, а не экспериментальная контрольная группа.')
    st.warning('Отклонение 2026 года связано по времени с кризисным периодом, но не является доказанным причинным эффектом. На позднем горизонте (дни 57–90) прогноз сильнее зависит от спецификации.')
