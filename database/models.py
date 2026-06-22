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
    agent_runs = relationship("AgentRun", back_populates="user", cascade="all, delete-orphan")
    coach_memories = relationship("CoachMemory", back_populates="user", cascade="all, delete-orphan")
    outbox_messages = relationship("OutboxMessage", back_populates="user", cascade="all, delete-orphan")
    locations = relationship("UserLocation", back_populates="user", cascade="all, delete-orphan")
    generated_documents = relationship("GeneratedDocument", back_populates="user", cascade="all, delete-orphan")


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


class AgentRun(Base):
    """Trace of one agent graph execution."""
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    run_type = Column(String(50), nullable=False, default="message")
    workflow = Column(String(50), nullable=False, default="user_message")
    intent = Column(String(50), nullable=True)
    status = Column(String(30), nullable=False, default="running")
    thread_id = Column(String(255), nullable=True, index=True)
    input_preview = Column(Text, nullable=True)
    output_preview = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="agent_runs")
    events = relationship("AgentEvent", back_populates="run", cascade="all, delete-orphan")


class AgentEvent(Base):
    """Node-level trace event for an agent run."""
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    node = Column(String(100), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    run = relationship("AgentRun", back_populates="events")


class CoachMemory(Base):
    """Durable user-specific memory for the fitness twin."""
    __tablename__ = "coach_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    memory_type = Column(String(50), nullable=False, default="fitness_twin")
    memory_key = Column(String(120), nullable=False)
    content = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    source_run_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="coach_memories")


class PlanVersion(Base):
    """Versioned generated workout or nutrition plan."""
    __tablename__ = "plan_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_type = Column(String(50), nullable=False)  # workout, nutrition, mixed
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    source_run_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PendingAction(Base):
    """Action proposed by an agent that may need user approval."""
    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(80), nullable=False)
    payload_json = Column(JSON, nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    requires_confirmation = Column(Boolean, default=True)
    due_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class SafetyEvent(Base):
    """Record of a health or safety-sensitive interaction."""
    __tablename__ = "safety_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    run_id = Column(Integer, nullable=True)
    severity = Column(String(30), nullable=False, default="caution")
    concerns_json = Column(JSON, nullable=True)
    message_excerpt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class OutboxMessage(Base):
    """Outbound message generated by the agent runtime."""
    __tablename__ = "outbox_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    external_id = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False, default="telegram")
    channel = Column(String(50), nullable=False, default="chat")
    body = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="returned")
    source_run_id = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="outbox_messages")


class UserLocation(Base):
    """User-provided location stored after explicit consent."""
    __tablename__ = "user_locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    label = Column(String(255), nullable=True)
    timezone = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    admin_area = Column(String(100), nullable=True)
    consent_source = Column(String(50), nullable=False, default="user_shared")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="locations")


class GeneratedDocument(Base):
    """PDF or document generated for a user."""
    __tablename__ = "generated_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_type = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="generated")
    source_run_id = Column(Integer, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="generated_documents")
