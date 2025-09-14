# BloodConnect - Blood Donation Management System

## Project Overview
BloodConnect is a Django-based web application to manage blood donations, appointments, requests, and donors using PostgreSQL as the database backend. The system serves patients, donors, nurses, and admins to facilitate efficient blood donation workflows and stock management.

---

## Features
- Patient appointment booking for blood requests
- Donor appointment booking for donations and blood requests
- Blood request and donation appointment approval workflows managed by nurses
- Admin dashboard for overall management and reporting
- Location tracking for guests, donors, and patients to find nearby compatible users and donation centres
- Geolocation-enabled SOS button for quick emergency help with nearest blood centres and contact info without signing up
- AI chatbot on the home page responding to blood donation queries (currently mock replies)
- Prevention of double booking for donors and patients on same day/time to avoid collisions
- Patients and donors can update their locations and find compatible nearby donors/patients
- Appointment cancellation options for patients and donors before scheduled time; nurses are notified in activity logs
- Nurses assigned to specific centres and handle appointments only for their centres
- Blood stock tracking by centre, blood group, and stock units with barcodes and expiry dates for inventory management
- FIFO stock consumption on blood request completion to handle blood unit expiration effectively
- Nurses can request blood replenishment from centres with sufficient stock; admin approves or declines these requests
- Nurses can monitor blood units nearing expiry or low quantities for proactive decision making

---

## Setup Instructions

### Prerequisites
- Python 3.13.5 or newer installed
- PostgreSQL installed and running
- Git installed (optional for cloning repository)
- Virtual environment tool (recommended)

### Clone the Repository

git clone https://github.com/theekibet/Blood-Connect.git
cd Blood-Connect




### Create and Activate a Virtual Environment (optional)
On macOS/Linux:

python3 -m venv env
source env/bin/activate


On Windows:

python -m venv env
.\env\Scripts\activate



### Install Project Dependencies
**Important:** Before running the project, install all required Python packages by running:

pip install -r requirements.txt



### Configure the Database
1. Create a PostgreSQL database and user:

CREATE DATABASE bloodconnect;
CREATE USER yourusername WITH PASSWORD 'yourpassword';
ALTER ROLE yourusername SET client_encoding TO 'utf8';
ALTER ROLE yourusername SET default_transaction_isolation TO 'read committed';
ALTER ROLE yourusername SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE bloodconnect TO yourusername;

text

2. Update your `settings.py` with your database credentials:

DATABASES = {
'default': {
'ENGINE': 'django.db.backends.postgresql',
'NAME': 'bloodconnect',
'USER': 'yourusername',
'PASSWORD': 'yourpassword',
'HOST': 'localhost',
'PORT': '5432',
}
}



### Run Migrations
Apply Django migrations to set up database tables:

python manage.py migrate



### Run the Development Server
Start your app locally:

python manage.py runserver


Visit [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser to see the app.

---
