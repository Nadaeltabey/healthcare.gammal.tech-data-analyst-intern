# Healthcare Data Analyst Full Package

📊 This repository provides a **complete data analyst toolkit** for **Healthcare.gammal.tech**.  
It contains SQL scripts, Python code for data simulation and visualization, and documented report templates.

---

## 📂 File Structure

```
healthcare_data_analyst_full_package.py
 ├── # Section 1: SQL Setup
 ├── # Section 2: Python Data Simulation
 ├── # Section 3: Visualization Exports
 ├── # Section 4: Report Templates Documentation
 └── # Section 5: How to Use
```

---

## 🚀 Sections Overview

### 1️⃣ SQL Setup
- Create schema `healthcare`.
- Build `appointments` table with KPIs (bookings, cancellations, satisfaction, wait times, revenue).
- Define **materialized views** for KPIs.
- Add **alerts table** + SQL functions for KPI threshold monitoring.

### 2️⃣ Python Data Simulation
- Generate sample datasets (`CSV` and `Excel`) with fake healthcare KPIs.
- KPIs included: Bookings, Cancellations, Wait Time, Satisfaction, New Patients, Revenue.
- Save datasets for use in Excel/Google Sheets dashboards.

### 3️⃣ Visualization Exports
- Create daily bookings line chart.
- Export average wait time bar chart.
- Save as `.png` images for reporting.

### 4️⃣ Report Templates Documentation
Markdown templates for reusable reports:
- **Daily Performance Report** (Bookings, Cancellations, Wait Time, Satisfaction, Revenue).  
- **Weekly Trends Report** (Growth, New vs Returning Patients, Revenue).  
- **Doctor Performance Report** (Patients, Satisfaction, Wait Time).  
- **Department Report** (Bookings, Revenue, Cancellations).  
- **Monthly Financial Report** (Revenue breakdown).  
- **Patient Experience Report** (Satisfaction, Wait Time, Feedback).  

### 5️⃣ How to Use
- Instructions for running Python script, generating datasets, and refreshing SQL views.
- Example scheduling with `pg_cron` or `crontab`.

---

## 📂 Files Included
- `healthcare_data_analyst_full_package.py` → Main file (SQL + Python + Documentation).  
- `healthcare_kpi_dashboard.xlsx` → Example dataset for dashboards.  
- `healthcare_kpi_dashboard.csv` → Same dataset in CSV format.  
- `bookings_trend.png` → Example visualization (daily bookings).  
- `wait_time.png` → Example visualization (average wait time).  

---

## 🛠️ How to Run

1. Clone this repository:
   ```bash
   git clone https://github.com/your-username/healthcare-data-analyst.git
   ```

2. Install dependencies:
   ```bash
   pip install pandas matplotlib openpyxl
   ```

3. Run the package script:
   ```bash
   python healthcare_data_analyst_full_package.py
   ```

4. Generated outputs:
   - `healthcare_kpi_dashboard.xlsx`
   - `healthcare_kpi_dashboard.csv`
   - `bookings_trend.png`
   - `wait_time.png`

---

## 🎯 Goal
This package enables healthcare data analysts to **simulate KPIs, visualize metrics, and document reporting templates**.  
It helps platforms like **Healthcare.gammal.tech** deliver clearer insights, improve doctor performance tracking, and enhance patient experience.

---

👤 Author: Data Analyst Intern @ Healthcare.gammal.tech
