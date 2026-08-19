# NABA Tech — Textile QC App

آن لائن، ملٹی لوکیشن، ملٹی یوزر Textile QC ایپ — Streamlit (frontend) + Supabase (database/backend)، GitHub کے ذریعے مینج۔

## ٹیک اسٹیک (Confirmed)
- **Frontend:** Streamlit
- **Database/Backend:** Supabase (PostgreSQL) — `DATABASE_URL` کے ذریعے SQLAlchemy سے کنیکٹ
- **Hosting:** Streamlit Community Cloud (GitHub repo سے براہ راست ڈیپلائے)
- **Code management:** GitHub (اسی حساب سے یہ پروجیکٹ `.gitignore`, `.github/workflows/ci.yml`, اور `.streamlit/secrets.toml.example` کے ساتھ تیار ہے)

## فیچرز کا خلاصہ

| فیچر | فائل | حالت |
|---|---|---|
| Multi-tenant Database schema | `database.py` | ✅ |
| 5-tier Auth + Hierarchy | `auth.py` | ✅ |
| AQL Calculator (PASS/FAIL) | `utils/aql.py` | ✅ ٹیسٹڈ |
| Defect Codes (آپ کے 4 رجسٹرز سے) | `utils/defect_codes.py` | ✅ |
| Data Entry (4 departments) | `screens/data_entry.py` | ✅ |
| Dashboard (Pie/Pareto/Line/Hall-wise) | `screens/dashboard.py` | ✅ |
| Admin Panel (users/locations/defects/branding) | `screens/admin.py` | ✅ |
| Super Master Admin (hidden panel) | `screens/super_admin.py` | ✅ |
| PDF Export (register کی طرح) | `reports/pdf_generator.py` | ✅ بنیادی، مزید ٹیوننگ باقی |
| **Import / Export (Excel/CSV)** | `screens/import_export.py`, `utils/import_export.py` | ✅ نیا شامل |
| Splash Screen (Logo + Video) | `app.py`, `assets/` | ✅ |

## GitHub پر رکھنے کا طریقہ

```bash
cd naba_qc_app
git init
git add .
git commit -m "Initial NABA Tech QC app"
git branch -M main
git remote add origin https://github.com/<your-username>/naba-qc-app.git
git push -u origin main
```

`.gitignore` پہلے سے یہ چیزیں خارج کرتا ہے تاکہ کوئی خفیہ پاس ورڈ/کلید GitHub پر نہ چڑھے: `.env`, `.streamlit/secrets.toml`, cache files۔

## Streamlit Community Cloud پر ڈیپلائے (سب سے آسان طریقہ)

1. share.streamlit.io پر جائیں، GitHub سے لاگ ان کریں۔
2. "New app" → اپنا `naba-qc-app` ریپو منتخب کریں → main branch → `app.py` بطور main file۔
3. Deploy سے پہلے **"Advanced settings" → "Secrets"** میں یہ پیسٹ کریں (اپنی اصل Supabase تفصیلات کے ساتھ):
   ```toml
   DATABASE_URL = "postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres"
   SUPER_ADMIN_SEED_USERNAME = "super_admin"
   SUPER_ADMIN_SEED_PASSWORD = "ایک مضبوط پاس ورڈ"
   ```
4. Deploy دبائیں۔ ایپ خودکار `init_db()` کال کرتی ہے، لیکن Super Master Admin بنانے کے لیے آپ کو ایک بار مقامی طور پر (یا Streamlit Cloud کے terminal سے) `python seed.py` چلانا ہوگا۔

## مقامی طور پر چلانا (Local Setup)

```bash
pip install -r requirements.txt
cp .env.example .env
# .env میں اپنا Supabase DATABASE_URL بھریں

python seed.py          # ایک بار — Supabase پر ٹیبلز بناتا ہے + پہلا Super Admin
streamlit run app.py
```

## Import / Export کیسے کام کرتا ہے

- **Export:** Sidebar → Import/Export → Export ٹیب → تاریخ رینج اور شعبہ منتخب کریں → Excel ڈاؤن لوڈ کریں (ہر رپورٹ ایک row، ڈیفیکٹ کی مقداریں الگ کالمز میں)۔
- **Import:** پہلے اپنے شعبے کا blank template ڈاؤن لوڈ کریں (اس میں آپ کے دفعتر کے ڈیفیکٹ کوڈز کے کالمز پہلے سے موجود ہیں) → Excel میں پُر کریں → دوبارہ اپلوڈ کریں۔ جو rows میں مسئلہ ہو انہیں چھوڑ کر باقی سب import ہو جائیں گی اور غلطیوں کی فہرست دکھائی جائے گی۔
- رسائی: Hall Manager اور اس سے اوپر کے رولز (Floor Inspector صرف Data Entry تک محدود ہے)۔

## فارمیٹنگ (رجسٹر سے مطابقت)

Data Entry فارم اور PDF ایکسپورٹ آپ کے چاروں اصل رجسٹرز (Cutting, Stitching, Checking, Packing) کے کالمز اور ڈیفیکٹ کوڈز پر مبنی ہیں۔ فی الحال PDF کا لے آؤٹ قریب ترین میچ ہے (headers, table, defect key, sign-off row, credit line) — اگر آپ چاہیں کہ فونٹ سائز، کالم چوڑائی، یا صفحہ لے آؤٹ عین اصل رجسٹر جیسا pixel-perfect ہو تو بتائیں، اگلے مرحلے میں مزید ٹیوننگ کر دوں گا۔

## ابھی باقی (Next Steps)
- PDF کی pixel-perfect ٹیوننگ (اگر آپ کو موجودہ لے آؤٹ کافی قریب نہ لگے)۔
- Cloud object storage (S3-compatible) کے لیے compressed photo کی مستقل جگہ — فی الحال صرف compress ہوتی ہے۔
