"""Отдельный документальный реестр событий (не база одобренных event-airport links)."""
from pathlib import Path
import pandas as pd
import streamlit as st

@st.cache_data
def load_events(path: str):
    table = pd.read_csv(path, encoding="utf-8-sig").fillna("")
    required = {"event_id", "year", "period", "event", "impact", "sources"}
    if not required.issubset(table.columns):
        raise ValueError(f"Отсутствуют столбцы реестра: {required - set(table.columns)}")
    if table["event_id"].duplicated().any():
        raise ValueError("В документальном реестре повторяются ID событий")
    return table

def render_events_panel(directory: Path):
    st.subheader("События и факторы авиадвижения · 2024–2026")
    st.caption("Документальный реестр от 19.10.2026 · события до 15.10.2026 включительно. Источник — предоставленный Markdown, не основная DuckDB.")
    try:
        df = load_events(str(directory / "events.csv"))
    except (OSError, ValueError) as e:
        st.error(f"Не удалось открыть реестр событий: {e}")
        return
    years = st.multiselect("Годы", sorted(df.year.unique().tolist()), default=sorted(df.year.unique().tolist()), key="event_years")
    search = st.text_input("Поиск по событию, периоду и последствиям", placeholder="Например: Heathrow, забастовка, 28 февраля, Basel", key="event_search")
    filtered = df[df.year.isin(years)].copy()
    if search.strip():
        cols=["event_id","period","event","impact"]
        mask=filtered[cols].astype(str).apply(lambda c:c.str.contains(search.strip(),case=False,regex=False)).any(axis=1)
        filtered=filtered[mask]
    a,b,c=st.columns(3)
    a.metric("Событий в реестре",len(df))
    b.metric("В выбранных годах",int(df.year.isin(years).sum()))
    c.metric("После поиска",len(filtered))
    st.info("Событие в документе не означает подтверждённого изменения трафика конкретного аэропорта. Интервалы в реестре могут быть приблизительными; причины и количественные эффекты не идентифицируются автоматически.")
    display=filtered.rename(columns={"event_id":"ID","year":"Год","period":"Дата / период","event":"Событие и география","impact":"Влияние / механизм"})
    st.dataframe(display[["ID","Год","Дата / период","Событие и география","Влияние / механизм"]],use_container_width=True,hide_index=True)
    st.download_button("Скачать выбранные события CSV", filtered.to_csv(index=False).encode("utf-8-sig"),file_name="events_filtered.csv",mime="text/csv",key="events_export")
    st.markdown("#### Источники и описание событий")
    if filtered.empty:
        st.caption("По фильтрам нет совпадений")
    else:
        ids=filtered.event_id.tolist()
        event_id=st.selectbox("Выберите событие",ids,format_func=lambda eid: eid+" — "+str(df.loc[df.event_id==eid,"event"].iloc[0])[:110],key="event_detail")
        event=filtered.loc[filtered.event_id==event_id].iloc[0]
        st.markdown(f"**{event['event']}**")
        st.write("**Период:**",event['period'])
        st.write("**Влияние и ограничения:**",event['impact'])
        st.markdown("**Документальные источники:** "+str(event['sources']))
    with st.expander("Методологические ограничения реестра"):
        st.markdown("""Реестр объединяет подтверждённые события и длительные факторы, влияющие на затраты или доступную ёмкость. Даты могут быть приблизительными; описание механизма не устанавливает величину причинного воздействия. Это **не** таблица утверждённых связей `event_id → airport_id → date` и не полный журнал NOTAM. Финансовые, налоговые и тарифные факторы следует отличать от локальных остановок аэропортов. Только запись событий не изменяет ряды EUROCONTROL и ITS.""")
