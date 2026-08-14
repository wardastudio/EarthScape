# EarthScape - Climate Analytics Platform

A full-stack climate monitoring and analytics platform built with Flask, MongoDB, and Machine Learning. Developed as a Final Year Project at Aptech Learning.

## Live Demo

**Live URL:** [https://earthscape.onrender.com](https://earthscape.onrender.com) *(After deployment)*

**Test Credentials:**
- Email: `admin@earthscape.org`
- Password: `admin123`

## ✨ Features

- **Secure Authentication** – JWT with role-based access (Admin, Analyst, Researcher, Guest)
- **Interactive Dashboards** – Real-time climate statistics, charts, and alerts
- **Machine Learning** – Predict carbon emissions, flood risks, and heatwaves
- **3D Visualizations** – Interactive maps, satellite viewers, and heatmaps
- **Big Data** – Hadoop MapReduce (with Python fallback for cloud deployment)
- **Real-time Weather** – OpenWeather API integration
- **Satellite Data** – Copernicus STAC API integration
- **Dataset Management** – Upload, approve, and manage CSV/Excel datasets

## Tech Stack

- **Backend:** Flask, Python 3.11
- **Database:** MongoDB Atlas
- **ML & Data:** scikit-learn, pandas, numpy, joblib
- **Authentication:** JWT, bcrypt
- **Frontend:** HTML, CSS, JavaScript, Three.js
- **Deployment:** Gunicorn, Render

## Project Structure
EarthScape/
├── app.py # Main Flask application
├── config.py # Configuration settings
├── requirements.txt # Python dependencies
├── controllers/ # Request handlers
├── routes/ # API route definitions
├── services/ # Business logic
├── models/ # ML models (linear_regression, decision_tree, knn)
├── templates/ # Jinja2 HTML templates
├── static/ # CSS, JS, and shaders
├── hadoop/ # MapReduce mapper/reducer
└── utils/ # Helper functions

## Local Setup

# Clone the repository
git clone https://github.com/YOUR_USERNAME/EarthScape.git
cd EarthScape

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables (.env file)
# Run the application
python app.py
📝 License
This project was developed for educational purposes as a Final Year Project at Aptech Learning.

👨‍💻 Author
Warda Khan - Aptech Learning Final Year eProject