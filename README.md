# 🍏 PriceWatch: Automated Price Tracking & AI Analytics

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web_UI-red?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![n8n](https://img.shields.io/badge/n8n-Automation-orange?style=flat-square&logo=n8n&logoColor=white)](https://n8n.io/)
[![Groq](https://img.shields.io/badge/Groq-AI_Analytics-green?style=flat-square)](https://groq.com/)

An end-to-end automated price monitoring solution designed to track product prices on Birmarket, Temu and Trendyol. This project combines web data extraction, an interactive web dashboard, large language model (LLM) insights, and background workflow automation.

---

## ✨ Key Features

- **Interactive Web UI (Streamlit):** Clean, responsive product cards featuring real-time price delta indicators and smooth asset management.
- **AI-Driven Analytics (Groq API):** Intelligent purchasing recommendations and cost trend evaluations powered by advanced LLMs.
- **Workflow Automation (n8n):** Scheduled background checks using the Schedule Trigger node for continuous monitoring and instant notifications.
- **Smart Asset Handling:** Automatic updates and deduplication logic for tracked items.
- **Marketplace parsers:** Paste a product link from Birmarket, Temu or Trendyol; the app detects the store and extracts title, current price, image and currency.

---

## 🛠️ Tech Stack

- **Frontend & UI:** Streamlit, Custom CSS
- **Backend & Parsing:** Python, Requests, BeautifulSoup
- **AI Integration:** Groq API (Llama 3)
- **Automation Engine:** n8n (Schedule Triggers, Webhooks)

---

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/gas240z/PriceTracker.git](https://github.com/gas240z/PriceTracker.git)
   cd PriceTracker

Install dependencies:

Bash
pip install -r requirements.txt
Configure environment variables:
Create a .env file in the project root and add your API key:

GROQ_API_KEY=your_groq_api_key_here
Launch the application:

Bash
streamlit run app.py

🔄 How to Push to GitHub
Once you create and save the README.md file, upload it to your repository with three simple commands in your terminal:

Bash
git add README.md
git commit -m "Add professional README for portfolio"
git push origin main
