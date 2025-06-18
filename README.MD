# 🌍 Air Quality Risk API — Django REST Framework (MVP)

A backend service for evaluating personal air quality exposure and health risks based on movement data and WHO guidelines. Implemented with Django + DRF and JWT authentication.

---

## 🚀 Features

* User registration and JWT-based authentication
* CSV upload of movement data (latitude, longitude, timestamp)
* Fetching air quality data from OpenWeatherMap API
* Risk assessment and fetal exposure scoring
* JSON responses for a mobile client

---

## 📦 Requirements

* Python 3.9+
* PostgreSQL
* pip (or equivalent package manager)

---

## ⚙️ Setup

### 1. Clone the repository

```bash
git clone https://github.com/IAmJustAmateur/aq_agent_api.git
cd aq_agent_api
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate.bat     # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

Your `requirements.txt` should include:

```
Django>=4.0
djangorestframework
djangorestframework-simplejwt
psycopg2-binary
python-dotenv
pandas
requests
```

### 3. Create and configure the `.env` file

In the project root (next to `manage.py`), create a file named `.env`:

```env
# Django settings
SECRET_KEY=your_django_secret_key_here
DEBUG=True

# PostgreSQL settings
POSTGRES_DB=air_quality_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# OpenWeather API key
OPENWEATHER_API_KEY=your_openweather_api_key_here
```

### 4. Configure the database and apply migrations

Django will automatically read settings from `.env`. Run:

```bash
python manage.py makemigrations
python manage.py migrate
```

If you need to hook into an existing database without recreating tables:

```bash
python manage.py migrate --fake-initial
```

### 5. Create a superuser (optional)

To access the Django admin interface:

```bash
python manage.py createsuperuser
```

---

## 🧪 Usage

### 🔧 Starting the API server (development)

```bash
python manage.py runserver
```

The API will be available at:

```
http://127.0.0.1:8000/
```

### 🔗 Endpoints

All endpoints are prefixed with `/api/`.

1. **User Registration**

   ```
   POST /api/register/
   ```

   * No authentication header required.
   * Request body (JSON):

     ```json
     {
       "email": "user@example.com",
       "username": "user123",
       "password": "strongpassword"
     }
     ```
   * Response (JSON):

     ```json
     {
       "id": 1,
       "email": "user@example.com",
       "username": "user123"
     }
     ```

2. **Login (JWT)**

   ```
   POST /api/login/
   ```

   * No authentication header required.
   * Request body (JSON):

     ```json
     {
       "email": "user@example.com",
       "password": "strongpassword"
     }
     ```
   * Response (JSON):

     ```json
     {
       "refresh": "<refresh_token>",
       "access": "<access_token>"
     }
     ```

3. **Upload Movement Data (CSV)**

   ```
   POST /api/upload_movements/
   ```

   * Headers:

     ```
     Authorization: Bearer <access_token>
     Content-Type: multipart/form-data
     ```
   * Form data (multipart/form-data):

     ```
     file: @/path/to/movements.csv; type=text/csv
     ```
   * Response (JSON):

     ```json
     { "message": "Data saved" }
     ```

4. **Analyze Air Quality Exposure (JSON Report)**

   ```
   GET /api/analyze/
   ```

   * Header:

     ```
     Authorization: Bearer <access_token>
     ```
   * Response (JSON example):

     ```json
     {
       "id": "8b57f8cc-1234-4a8e-9b7a-f1b2c3d4e5f6",
       "user": 1,
       "analysis_date": "2025-05-10",
       "pm25_avg": 12.3,
       "no2_peak": 45.6,
       "o3_peak": 78.9,
       "exposure_hours": 3.5,
       "fetal_risk_score": 0.68,
       "pdf": null,
       "created_at": "2025-05-10T14:23:45.123Z"
     }
     ```

---

## 📄 Sample CSV Format

```csv
latitude,longitude,timestamp
52.5200,13.4050,2025-05-09T08:00:00
52.5205,13.4060,2025-05-09T09:15:00
```

* `latitude`: decimal degrees
* `longitude`: decimal degrees
* `timestamp`: ISO 8601 (e.g., `2025-05-09T08:00:00`)

---

## 🛠 Development Tips

* **`.env`** files must not be committed to the repository.
* Use `OPENWEATHER_API_KEY` to fetch data from OpenWeatherMap.
* Core logic for fetching air quality data and risk assessment lives in `api/utils.py`.
* Database access is handled via Django’s ORM; models are in `api/models.py`.

### Django Admin

Visit:

```
http://127.0.0.1:8000/admin/
```

to manage users, movements, and summaries.

---

## ✅ Roadmap

* [x] MVP with Django REST Framework
* [x] JWT Authentication
* [x] CSV movement import
* [x] OpenWeatherMap integration and caching
* [x] Risk calculation and saving daily summary
* [ ] PDF report generation
* [ ] Frontend (mobile app) integration
* [ ] Admin panel with charts and history
* [ ] Notifications for elevated risk

---

## 📝 License

MIT License

