from sqlalchemy import Column, Integer, Float, String
from database import Base

class UserFinance(Base):
    __tablename__ = "finances"

    id = Column(Integer, primary_key=True, index=True)
    income = Column(Float)
    expenses = Column(Float)
    savings_goal = Column(Float)
