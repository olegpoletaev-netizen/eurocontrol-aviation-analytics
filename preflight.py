"""Offline check of Streamlit Cloud deployment files; does not modify DuckDB."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
required=["app.py","requirements.txt","eda_panel.py","its_llbg_panel.py","its_validation_panel.py","model_comparison_panel.py","event_registry/events.csv","eurostat_route_analytics_v1/data/route_monthly_panel.csv","its_llbg_data/its_llbg_daily.csv","its_validation_data/post_daily_validation.csv","model_comparison_data/model_comparison_summary.csv"]
missing=[n for n in required if not (ROOT/n).is_file()]
for n in required: print(("MISSING" if n in missing else "OK"),n)
db=ROOT/"aviation_analytics.duckdb"
if not db.is_file():
 print("BLOCKER: aviation_analytics.duckdb отсутствует. Возьмите проверенную копию из локального проекта.")
 sys.exit(2)
try:
 import duckdb
 with duckdb.connect(str(db),read_only=True) as c:
  tables={r[0] for r in c.execute("SHOW TABLES").fetchall()}
  require={"dim_airport","fact_airport_daily","vw_airport_daily","fact_data_quality"}
  absent=sorted(require-tables)
  print("DATABASE", db.stat().st_size, "bytes; missing required views/tables:",absent)
  if absent: sys.exit(3)
  n=c.execute("SELECT COUNT(*) FROM fact_airport_daily").fetchone()[0]
  print("airport-day rows:", n)
except Exception as exc:
 print("DB CHECK FAILED",str(exc));sys.exit(4)
if missing:sys.exit(1)
print("PREFLIGHT OK")
