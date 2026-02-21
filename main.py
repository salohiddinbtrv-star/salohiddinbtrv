from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
    monthly_needed = savings_goal / 6

    advice = "Zo'r! Moliyaviy rejangiz yaxshi."
    if remaining < monthly_needed:
        advice = "Xarajatlarni kamaytirish kerak!"

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "remaining": remaining,
            "monthly_needed": monthly_needed,
            "advice": advice
        }
    )
