"""SQLAlchemy database models for the fitness coach."""

import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from database.database import Base


class User(Base):
    """Core user identity."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True, nullable=False, index=True)
    platform = Column(String(50), default="telegram")  # telegram, cli, etc.
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True)
    last_message_at = Column(DateTime, nullable=True)  # Last time user sent a message

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    workout_logs = relationship("WorkoutLog", back_populates="user", cascade="all, delete-orphan")
    nutrition_logs = relationship("NutritionLog", back_populates="user", cascade="all, delete-orphan")
    check_ins = relationship("CheckIn", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    """Detailed fitness profile for a user."""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Basic info
    age = Column(Integer, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    sex = Column(String(20), nullable=True)

    # Fitness
    fitness_level = Column(String(50), nullable=True)  # debutant, intermediaire, avance
    goal = Column(String(100), nullable=True)  # perte_poids, prise_masse, recomposition, remise_en_forme
    available_equipment = Column(Text, nullable=True)  # JSON list or description
    training_frequency = Column(String(50), nullable=True)  # e.g. "3x/semaine"
    injuries_constraints = Column(Text, nullable=True)

    # Nutrition
    dietary_preferences = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    food_budget = Column(String(50), nullable=True)

    # Lifestyle
    lifestyle_rhythm = Column(String(100), nullable=True)  # sedentaire, actif, tres_actif
    wake_up_time = Column(String(10), nullable=True)
    sleep_time = Column(String(10), nullable=True)

    # Extra
    extra_info = Column(Text, nullable=True)  # JSON for any additional data
    profile_complete = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="profile")


class Conversation(Base):
    """A conversation thread with a user."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    context_type = Column(String(50), default="general")  # general, onboarding, checkin, plan

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    user = relationship("User", back_populates="conversations")


class Message(Base):
    """Individual message in a conversation."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")


class WorkoutLog(Base):
    """Log of a workout session."""
    __tablename__ = "workout_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    planned_workout = Column(Text, nullable=True)
    completed = Column(Boolean, default=False)
    actual_workout = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    difficulty_rating = Column(Integer, nullable=True)  # 1-10
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="workout_logs")


class NutritionLog(Base):
    """Log of nutrition/meals."""
    __tablename__ = "nutrition_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    meal_type = Column(String(50), nullable=True)  # petit_dejeuner, dejeuner, diner, collation
    description = Column(Text, nullable=True)
    plan_followed = Column(Boolean, nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="nutrition_logs")


class CheckIn(Base):
    """Daily check-in record."""
    __tablename__ = "check_ins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    check_in_type = Column(String(20), nullable=False)  # morning, evening
    energy_level = Column(Integer, nullable=True)  # 1-10
    motivation_level = Column(Integer, nullable=True)  # 1-10
    mood = Column(String(50), nullable=True)
    pain_reported = Column(Text, nullable=True)
    workout_done = Column(Boolean, nullable=True)
    nutrition_followed = Column(Boolean, nullable=True)
    sleep_quality = Column(Integer, nullable=True)  # 1-10
    notes = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)

    user = relationship("User", back_populates="check_ins")

