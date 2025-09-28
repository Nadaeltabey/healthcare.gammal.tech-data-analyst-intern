"healthcare_data_analyst_full_package.py"

# -----------------------------
# Section 1: SQL  
# -----------------------------
SQL_KPIS = r'''
-- healthcare_kpis.sql
-- Materialized views, alerts table, and refresh / alert functions
-- Assumptions: appointments, admissions, patient_surveys, doctors, clinics
BEGIN;

CREATE TABLE IF NOT EXISTS kpi_alerts (
  alert_id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  alert_type TEXT NOT NULL,
  object_type TEXT,
  object_id TEXT,
  metric TEXT,
  value NUMERIC,
  threshold NUMERIC,
  severity TEXT,
  message TEXT,
  acknowledged BOOLEAN DEFAULT FALSE,
  acknowledged_by TEXT,
  acknowledged_at TIMESTAMPTZ
);

-- Patient survey aggregates (last 90d)
DROP MATERIALIZED VIEW IF EXISTS mv_patient_survey_agg;
CREATE MATERIALIZED VIEW mv_patient_survey_agg AS
SELECT
  d.doctor_id,
  d.name AS doctor_name,
  COUNT(ps.survey_id) AS responses_count,
  AVG(ps.rating) AS avg_rating,
  SUM(CASE WHEN ps.rating >= 9 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(ps.survey_id),0) AS promoters_pct,
  SUM(CASE WHEN ps.rating <= 6 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(ps.survey_id),0) AS detractors_pct,
  ( (SUM(CASE WHEN ps.rating >= 9 THEN 1 ELSE 0 END) - SUM(CASE WHEN ps.rating <= 6 THEN 1 ELSE 0 END))::float
    / NULLIF(COUNT(ps.survey_id),0) ) * 100 AS nps_pct,
  MIN(ps.created_at) AS first_response,
  MAX(ps.created_at) AS last_response
FROM patient_surveys ps
JOIN appointments a ON ps.appointment_id = a.appointment_id
JOIN doctors d ON a.doctor_id = d.doctor_id
WHERE ps.created_at >= now() - INTERVAL '90 days'
GROUP BY d.doctor_id, d.name
WITH NO DATA;

-- Readmission 30d
DROP MATERIALIZED VIEW IF EXISTS mv_readmission_30d;
CREATE MATERIALIZED VIEW mv_readmission_30d AS
WITH discharges AS (
  SELECT admission_id, patient_id, discharge_date, doctor_id
  FROM admissions
  WHERE discharge_date IS NOT NULL
    AND discharge_date >= now() - INTERVAL '180 days'
)
SELECT
  d.doctor_id,
  d.name AS doctor_name,
  COUNT(discharge_date) AS discharges_count,
  SUM(
    CASE WHEN EXISTS (
      SELECT 1 FROM admissions a2
      WHERE a2.patient_id = discharges.patient_id
        AND a2.admission_date BETWEEN discharges.discharge_date AND discharges.discharge_date + INTERVAL '30 days'
    ) THEN 1 ELSE 0 END
  ) AS readmissions_30d,
  (SUM(
    CASE WHEN EXISTS (
      SELECT 1 FROM admissions a2
      WHERE a2.patient_id = discharges.patient_id
        AND a2.admission_date BETWEEN discharges.discharge_date AND discharges.discharge_date + INTERVAL '30 days'
    ) THEN 1 ELSE 0 END
  )::float / NULLIF(COUNT(discharge_date),0)) * 100 AS readmission_30d_pct
FROM discharges
JOIN doctors d ON discharges.doctor_id = d.doctor_id
GROUP BY d.doctor_id, d.name
WITH NO DATA;

-- Avg wait
DROP MATERIALIZED VIEW IF EXISTS mv_avg_wait;
CREATE MATERIALIZED VIEW mv_avg_wait AS
SELECT
  clinic_id,
  doctor_id,
  COUNT(*) AS total_appointments,
  AVG(EXTRACT(EPOCH FROM (consult_start_time - arrival_time))/60) AS avg_wait_minutes,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (consult_start_time - arrival_time))/60) AS median_wait_minutes
FROM appointments
WHERE consult_start_time IS NOT NULL
  AND arrival_time IS NOT NULL
  AND consult_start_time >= now() - INTERVAL '90 days'
GROUP BY clinic_id, doctor_id
WITH NO DATA;

-- No-show rate
DROP MATERIALIZED VIEW IF EXISTS mv_noshow_rate;
CREATE MATERIALIZED VIEW mv_noshow_rate AS
SELECT
  clinic_id,
  COUNT(*) FILTER (WHERE status = 'no_show')::float / NULLIF(COUNT(*),0) AS no_show_rate,
  COUNT(*) AS total_scheduled
FROM appointments
WHERE scheduled_time >= now() - INTERVAL '90 days'
GROUP BY clinic_id
WITH NO DATA;

-- Followup adherence
DROP MATERIALIZED VIEW IF EXISTS mv_followup_adherence;
CREATE MATERIALIZED VIEW mv_followup_adherence AS
SELECT
  doctor_id,
  COUNT(*) FILTER (WHERE is_followup = TRUE) AS followups_scheduled,
  COUNT(*) FILTER (WHERE is_followup = TRUE AND status = 'done')::float
    / NULLIF(COUNT(*) FILTER (WHERE is_followup = TRUE),0) AS followup_adherence_pct
FROM appointments
WHERE scheduled_time >= now() - INTERVAL '90 days'
GROUP BY doctor_id
WITH NO DATA;

-- Doctor composite (example)
DROP MATERIALIZED VIEW IF EXISTS mv_doctor_composite;
CREATE MATERIALIZED VIEW mv_doctor_composite AS
WITH
  s AS (SELECT * FROM mv_patient_survey_agg),
  r AS (SELECT * FROM mv_readmission_30d),
  w AS (SELECT * FROM mv_avg_wait),
  f AS (SELECT doctor_id, followup_adherence_pct FROM mv_followup_adherence),
  metrics AS (
    SELECT
      d.doctor_id,
      d.name as doctor_name,
      COALESCE(s.nps_pct,0) AS nps_pct,
      COALESCE(r.readmission_30d_pct,0) AS readmission_30d_pct,
      COALESCE(w.avg_wait_minutes, NULL) AS avg_wait_minutes,
      COALESCE(f.followup_adherence_pct,0) AS followup_adherence_pct,
      COALESCE(s.responses_count,0) AS responses_count
    FROM doctors d
    LEFT JOIN s ON d.doctor_id = s.doctor_id
    LEFT JOIN r ON d.doctor_id = r.doctor_id
    LEFT JOIN w ON d.doctor_id = w.doctor_id
    LEFT JOIN f ON d.doctor_id = f.doctor_id
  ),
  bounds AS (
    SELECT
      MAX(nps_pct) AS max_nps, MIN(nps_pct) AS min_nps,
      MAX(readmission_30d_pct) AS max_readm, MIN(readmission_30d_pct) AS min_readm,
      MAX(avg_wait_minutes) AS max_wait, MIN(avg_wait_minutes) AS min_wait,
      MAX(followup_adherence_pct) AS max_follow, MIN(followup_adherence_pct) AS min_follow,
      MAX(responses_count) AS max_resp, MIN(responses_count) AS min_resp
    FROM metrics
  )
SELECT
  m.doctor_id,
  m.doctor_name,
  m.responses_count,
  m.nps_pct,
  m.readmission_30d_pct,
  m.avg_wait_minutes,
  m.followup_adherence_pct,
  CASE WHEN (bounds.max_nps - bounds.min_nps) = 0 THEN 0
       ELSE (m.nps_pct - bounds.min_nps) / NULLIF((bounds.max_nps - bounds.min_nps),0) END AS nps_norm,
  CASE WHEN (bounds.max_readm - bounds.min_readm) = 0 THEN 0
       ELSE 1.0 - ((m.readmission_30d_pct - bounds.min_readm) / NULLIF((bounds.max_readm - bounds.min_readm),0)) END AS readm_norm,
  CASE WHEN (bounds.max_wait - bounds.min_wait) IS NULL OR (bounds.max_wait - bounds.min_wait) = 0 THEN 0
       ELSE 1.0 - ((COALESCE(m.avg_wait_minutes, bounds.max_wait) - COALESCE(bounds.min_wait,0)) / NULLIF((bounds.max_wait - COALESCE(bounds.min_wait,0)),0)) END AS wait_norm,
  CASE WHEN (bounds.max_follow - bounds.min_follow) = 0 THEN 0
       ELSE (m.followup_adherence_pct - bounds.min_follow) / NULLIF((bounds.max_follow - bounds.min_follow),0) END AS follow_norm,
  LEAST(1.0, CASE WHEN bounds.max_resp IS NULL OR bounds.max_resp = 0 THEN 0 ELSE LN(1+m.responses_count) / NULLIF(LN(1+bounds.max_resp),0) END) AS volume_adj,
  (
    ((CASE WHEN (bounds.max_nps - bounds.min_nps) = 0 THEN 0 ELSE (m.nps_pct - bounds.min_nps) / NULLIF((bounds.max_nps - bounds.min_nps),0) END) * 0.30)
    + ( (CASE WHEN (bounds.max_readm - bounds.min_readm) = 0 THEN 0 ELSE 1.0 - ((m.readmission_30d_pct - bounds.min_readm) / NULLIF((bounds.max_readm - bounds.min_readm),0)) END) * 0.25)
    + ( (CASE WHEN (bounds.max_wait - bounds.min_wait) IS NULL OR (bounds.max_wait - bounds.min_wait) = 0 THEN 0 ELSE 1.0 - ((COALESCE(m.avg_wait_minutes, bounds.max_wait) - COALESCE(bounds.min_wait,0)) / NULLIF((bounds.max_wait - COALESCE(bounds.min_wait,0)),0)) END) * 0.15)
    + ( (CASE WHEN (bounds.max_follow - bounds.min_follow) = 0 THEN 0 ELSE (m.followup_adherence_pct - bounds.min_follow) / NULLIF((bounds.max_follow - bounds.min_follow),0) END) * 0.15)
    + ( LEAST(1.0, CASE WHEN bounds.max_resp IS NULL OR bounds.max_resp = 0 THEN 0 ELSE LN(1+m.responses_count) / NULLIF(LN(1+bounds.max_resp),0) END) * 0.15)
  ) * 100 AS composite_score
FROM metrics m CROSS JOIN bounds
WITH NO DATA;

-- Refresh function
CREATE OR REPLACE FUNCTION refresh_kpi_materialized_views() RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_patient_survey_agg;
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_readmission_30d;
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_avg_wait;
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_noshow_rate;
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_followup_adherence;
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_doctor_composite;
END;
$$;

-- Alert generation (example thresholds)
CREATE OR REPLACE FUNCTION generate_kpi_alerts() RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
  rec RECORD;
  th_nps_threshold NUMERIC := 6;
  th_readm_pct NUMERIC := 8.0;
  th_wait_minutes NUMERIC := 30.0;
  th_noshow_rate NUMERIC := 0.15;
BEGIN
  FOR rec IN
    SELECT doctor_id, avg_rating, responses_count FROM mv_patient_survey_agg WHERE avg_rating IS NOT NULL AND avg_rating <= th_nps_threshold
  LOOP
    INSERT INTO kpi_alerts(alert_type, object_type, object_id, metric, value, threshold, severity, message)
    VALUES ('low_nps','doctor', rec.doctor_id::text, 'avg_rating', rec.avg_rating, th_nps_threshold, 'medium',
      format('متوسط تقييم المرضى للطبيب %s = %s <= %s (عدد الاستجابات: %s)', rec.doctor_id, rec.avg_rating, th_nps_threshold, rec.responses_count)
    );
  END LOOP;

  FOR rec IN
    SELECT doctor_id, readmission_30d_pct FROM mv_readmission_30d WHERE readmission_30d_pct IS NOT NULL AND readmission_30d_pct >= th_readm_pct
  LOOP
    INSERT INTO kpi_alerts(alert_type, object_type, object_id, metric, value, threshold, severity, message)
    VALUES ('high_readmission','doctor', rec.doctor_id::text, 'readmission_30d_pct', rec.readmission_30d_pct, th_readm_pct, 'high',
      format('معدل إعادة الدخول خلال 30 يوم للطبيب %s = %s%% >= %s%%', rec.doctor_id, ROUND(rec.readmission_30d_pct::numeric,2), th_readm_pct)
    );
  END LOOP;

  FOR rec IN
    SELECT clinic_id, AVG(avg_wait_minutes) AS clinic_avg_wait FROM mv_avg_wait GROUP BY clinic_id HAVING AVG(avg_wait_minutes) >= th_wait_minutes
  LOOP
    INSERT INTO kpi_alerts(alert_type, object_type, object_id, metric, value, threshold, severity, message)
    VALUES ('high_wait','clinic', rec.clinic_id::text, 'avg_wait_minutes', rec.clinic_avg_wait, th_wait_minutes, 'medium',
      format('متوسط انتظار العيادة %s = %s دقيقة >= %s', rec.clinic_id, ROUND(rec.clinic_avg_wait::numeric,1), th_wait_minutes)
    );
  END LOOP;

  FOR rec IN
    SELECT clinic_id, no_show_rate FROM mv_noshow_rate WHERE no_show_rate >= th_noshow_rate
  LOOP
    INSERT INTO kpi_alerts(alert_type, object_type, object_id, metric, value, threshold, severity, message)
    VALUES ('high_noshow','clinic', rec.clinic_id::text, 'no_show_rate', rec.no_show_rate, th_noshow_rate, 'medium',
      format('نسبة عدم الحضور للعيادة %s = %s%% >= %s%%', rec.clinic_id, ROUND(rec.no_show_rate::numeric * 100,2), th_noshow_rate*100)
    );
  END LOOP;

END;
$$;

CREATE OR REPLACE FUNCTION refresh_and_alert() RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
  PERFORM refresh_kpi_materialized_views();
  PERFORM generate_kpi_alerts();
END;
$$;

COMMIT;
'''

# -----------------------------
# Section 2: Python scripts (data simulation and visualization)
# -----------------------------
PY_SCRIPT = r'''
# generate_sample_kpis.py
# سكربت بايثون لإنشاء بيانات تجريبية، تصقيفها، حفظ Excel/CSV، ورسم تصورات PNG
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

OUTPUT_DIR = Path('output')
OUTPUT_DIR.mkdir(exist_ok=True)

np.random.seed(42)
N = 30
dates = pd.date_range(start='2025-09-01', periods=N, freq='D')

df = pd.DataFrame({
    'Date': dates,
    'Bookings': np.random.randint(80,200,size=N),
    'Completed': np.random.randint(60,180,size=N),
    'Cancellations': np.random.randint(5,40,size=N),
    'Avg_Wait_Min': np.random.randint(5,60,size=N),
    'Satisfaction_pct': np.random.randint(70,100,size=N),
    'New_Patients': np.random.randint(10,60,size=N),
    'Returning_Patients': np.random.randint(20,120,size=N),
    'Revenue_USD': np.random.randint(2000,10000,size=N)
})

# Export
df.to_csv(OUTPUT_DIR / 'kpi_sample_data.csv', index=False)
df.to_excel(OUTPUT_DIR / 'kpi_sample_data.xlsx', index=False)

# Plot 1: Bookings trend
plt.figure(figsize=(10,4))
plt.plot(df['Date'], df['Bookings'], marker='o')
plt.title('Daily Bookings')
plt.xlabel('Date')
plt.ylabel('Bookings')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'plot_bookings.png')
plt.close()

# Plot 2: Completed vs Cancellations (stacked)
plt.figure(figsize=(10,4))
plt.bar(df['Date'], df['Completed'], label='Completed')
plt.bar(df['Date'], df['Cancellations'], bottom=df['Completed'], label='Cancellations', color='red')
plt.title('Completed vs Cancellations')
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'plot_completed_cancellations.png')
plt.close()

# Plot 3: Avg wait time
plt.figure(figsize=(10,4))
plt.bar(df['Date'], df['Avg_Wait_Min'], color='orange')
plt.title('Average Wait Time (min)')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'plot_waittime.png')
plt.close()

# Plot 4: Satisfaction
plt.figure(figsize=(10,4))
plt.plot(df['Date'], df['Satisfaction_pct'], marker='o', color='green')
plt.title('Patient Satisfaction (%)')
plt.ylim(60,100)
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'plot_satisfaction.png')
plt.close()

print('Sample data and plots saved to', OUTPUT_DIR)
'''

# -----------------------------
# Section 3: Report templates (Markdown strings)
# -----------------------------
REPORT_TEMPLATES = {
    'daily': r'''
# تقرير الأداء اليومي

**الهدف:** متابعة أداء المنصة يومياً.

**المؤشرات:**
- إجمالي الحجوزات: {{TOTAL_BOOKINGS}}
- الحجوزات المكتملة: {{COMPLETED}}
- الإلغاءات: {{CANCELLATIONS}}
- متوسط وقت الانتظار: {{AVG_WAIT}} دقيقة
- رضا المرضى: {{SATISFACTION}} %
- الإيرادات: ${{REVENUE}}

**التوصيات:**
- إذا نسبة الإلغاء > 10%: مراجعة سياسة التذكير.
- إذا avg_wait > 30: فحص جدول الأطباء.

**الرسوم المرفقة:** خط الحجوزات، شريط المكتمل/الملغي، مؤشر رضا المرضى.
# تقرير الأداء اليومي

**الهدف:** متابعة أداء المنصة يومياً.

**المؤشرات:**
- إجمالي الحجوزات: {{TOTAL_BOOKINGS}}
- الحجوزات المكتملة: {{COMPLETED}}
- الإلغاءات: {{CANCELLATIONS}}
- متوسط وقت الانتظار: {{AVG_WAIT}} دقيقة
- رضا المرضى: {{SATISFACTION}} %
- الإيرادات: ${{REVENUE}}

**التوصيات:**
- إذا نسبة الإلغاء > 10%: مراجعة سياسة التذكير.
- إذا avg_wait > 30: فحص جدول الأطباء.

**الرسوم المرفقة:** خط الحجوزات، شريط المكتمل/الملغي، مؤشر رضا المرضى.
''',
    'weekly': r'''
# تقرير الاتجاهات الأسبوعية

**الهدف:** رصد الأداء الأسبوعي.

**المؤشرات:**
- إجمالي الحجوزات للأسبوع: {{WEEK_BOOKINGS}}
- نسبة المرضى الجدد: {{NEW_PATIENTS_PCT}}%
- متوسط رضا المرضى: {{AVG_SAT}}%
- الإيرادات الأسبوعية: ${{WEEK_REVENUE}}

**تحليل:**
- مقارنة بالأسبوع السابق: {{CHANGE_VS_LAST_WEEK}}

**توصيات:**
- تكثيف التذكيرات في الأيام ذات الـ no-show العالي.
''',
    'doctor_perf': r'''
# تقرير أداء الطبيب

**الطبيب:** {{DOCTOR_NAME}}

**مؤشرات:**
- عدد المرضى: {{PATIENT_COUNT}}
- متوسط رضا المرضى: {{SAT}}
- متوسط وقت الانتظار: {{WAIT_MIN}} دقيقة
- نسبة إعادة الدخول 30 يوم: {{READM_30D}}%
- النتيجة المركبة: {{COMPOSITE_SCORE}}/100

**توصيات:**
- إذا composite < 50: جدولة مراجعة أداء وورشة تدريب.
- إذا readm_30d > 8%: اختيار حالات عشوائية للمراجعة.
'''
}

# -----------------------------
# Section 4: Cron examples & How to use
# -----------------------------
CRON_EXAMPLE = r'''
# Example for scheduling using pg_cron inside Postgres
-- Run refresh_and_alert() every hour
SELECT cron.schedule('refresh_kpis_hourly', '0 * * * *', $$SELECT refresh_and_alert();$$);

# Or use system crontab with psql (outside DB):
# 0 * * * * psql -d yourdb -c "SELECT refresh_and_alert();"
'''

USAGE = '''
How to use this package (summary):
1) SQL: review SQL_KPIS string and adapt table/column names to your schema. Run in a sandbox DB first.
2) Python: run the generate_sample_kpis.py script to create sample data and charts (requires pandas, matplotlib, openpyxl).
   - pip install pandas matplotlib openpyxl
   - python generate_sample_kpis.py
3) Reports: Use the Markdown templates (REPORT_TEMPLATES) and replace placeholders with real values (or render using a templating engine).
4) Scheduling: use pg_cron or system cron to run refresh_and_alert regularly.
'''

# -----------------------------
# Section 5: Helper to write files when executed locally
# -----------------------------
from pathlib import Path
def write_package_files(output_dir='package_output'):
    out = Path(output_dir)
    out.mkdir(exist_ok=True)
    (out / 'healthcare_kpis.sql').write_text(SQL_KPIS, encoding='utf-8')
    (out / 'generate_sample_kpis.py').write_text(PY_SCRIPT, encoding='utf-8')
    (out / 'report_templates.md').write_text('\n\n'.join([REPORT_TEMPLATES['daily'], REPORT_TEMPLATES['weekly'], REPORT_TEMPLATES['doctor_perf']]), encoding='utf-8')
    (out / 'cron_examples.txt').write_text(CRON_EXAMPLE, encoding='utf-8')
    (out / 'USAGE.txt').write_text(USAGE, encoding='utf-8')
    print('Package files written to', out.resolve())

if __name__ == '__main__':
    write_package_files()
    print('Done. You can upload the folder package_output to GitHub.')
