from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os

import models
from database import engine, SessionLocal

# Database yaratish
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# 📁 Absolute path olish (404 muammo bo‘lmasligi uchun)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Static papkani ulash
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

# Templates papkani ulash
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/calculate", response_class=HTMLResponse)
def calculate(
    request: Request,
    income: float = Form(...),
    expenses: float = Form(...),
    savings_goal: float = Form(...)
):
    db: Session = SessionLocal()

    finance = models.UserFinance(
        income=income,
        expenses=expenses,
        savings_goal=savings_goal
    )
    db.add(finance)
    db.commit()

    remaining = income - expenses
    monthly_needed = savings_goal / 6 if savings_goal > 0 else 0

    # Professional maslahat logikasi
    if remaining <= 0:
        advice = "⚠️ Xarajatlaringiz daromaddan oshib ketgan. Byudjetni qayta ko‘rib chiqing."
    elif remaining < monthly_needed:
        advice = "📉 Maqsadga yetish uchun xarajatlarni kamaytirish yoki daromadni oshirish kerak."
    else:
        advice = "✅ Zo‘r! Moliyaviy rejangiz sog‘lom ko‘rinmoqda."

    db.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "remaining": round(remaining, 2),
            "monthly_needed": round(monthly_needed, 2),
            "advice": advice
        }
    )
