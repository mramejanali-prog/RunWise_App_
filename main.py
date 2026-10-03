import os
from datetime import datetime, timedelta, timezone, date
from typing import Optional
from uuid import uuid4
import hashlib
import hmac
import json
import base64
import secrets

import jwt
from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy import text as sql_text
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, DateTime, Float, Integer, Boolean, select, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./runwise.db")
APP_ENV = os.getenv("APP_ENV", "development").lower()
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
AUTH_RATE_LIMIT_PER_5_MIN = int(os.getenv("AUTH_RATE_LIMIT_PER_5_MIN", "10"))
TCHACO_WEBHOOK_SECRET = os.getenv("TCHACO_WEBHOOK_SECRET", "")
if APP_ENV in {"production", "prod"}:
    if len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters in production")
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("DATABASE_URL must use PostgreSQL in production")
else:
    if not JWT_SECRET:
        JWT_SECRET = "dev-only-change-me"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
PASSWORD_ITERATIONS = int(os.getenv("PASSWORD_ITERATIONS", "600000"))
try:
    from passlib.context import CryptContext  # optional locally; required in production requirements
    _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    _pwd = None

def password_hash(password: str) -> str:
    if _pwd is not None:
        return _pwd.hash(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256$%d$%s$%s" % (PASSWORD_ITERATIONS, base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode())

def password_verify(password: str, encoded: str) -> bool:
    if encoded.startswith("$2") and _pwd is not None:
        return _pwd.verify(password, encoded)
    try:
        scheme, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

class Base(DeclarativeBase): pass

class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ActivityRow(Base):
    __tablename__ = "activities"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="TRAINING")
    race_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    distance_meters: Mapped[float] = mapped_column(Float)
    avg_heart_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elevation_gain_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_pace_seconds_per_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id", name="uq_activity_external"),)

class GoalRow(Base):
    __tablename__ = "goals"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(255))
    target_value: Mapped[float] = mapped_column(Float)
    current_value: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(32))
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class RaceRow(Base):
    __tablename__ = "races"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(64), default="LOCAL")
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    distance_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    registration_status: Mapped[str] = mapped_column(String(64), default="UNKNOWN")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("user_id", "provider", "external_id", name="uq_race_external"),)

class PlannedWorkoutRow(Base):
    __tablename__ = "planned_workouts"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    target_distance_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_pace_min_seconds_per_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_pace_max_seconds_per_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_reason: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

if APP_ENV not in {"production", "prod"}:
    Base.metadata.create_all(engine)

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limit=120, auth_limit=10):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.auth_limit = auth_limit
        self.hits = {}

    async def dispatch(self, request: Request, call_next):
        now = datetime.now(timezone.utc).timestamp()
        ip = request.client.host if request.client else "unknown"
        key = (ip, request.url.path.startswith("/v1/auth/"))
        window = 300 if key[1] else 60
        limit = self.auth_limit if key[1] else self.rate_limit
        bucket = self.hits.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return Response(content='{"detail":"Rate limit exceeded"}', status_code=429, media_type="application/json", headers={"Retry-After": str(window)})
        bucket.append(now)
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/v1/") else "no-cache"
        return response

docs_url = None if APP_ENV in {"production", "prod"} else "/docs"
redoc_url = None if APP_ENV in {"production", "prod"} else "/redoc"
APP_VERSION = "1.0.0"
app = FastAPI(title="RunWise API", version=APP_VERSION, docs_url=docs_url, redoc_url=redoc_url)
if APP_ENV in {"production", "prod"} and ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(SecurityMiddleware, rate_limit=RATE_LIMIT_PER_MINUTE, auth_limit=AUTH_RATE_LIMIT_PER_5_MIN)
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"], allow_headers=["Authorization","Content-Type"])

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()

def token_for(user: UserRow) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": user.id, "exp": exp}, JWT_SECRET, algorithm="HS256")

def current_user(authorization: Optional[str] = Header(default=None), session: Session = Depends(db)) -> UserRow:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authorization required")
    try: payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Invalid or expired token")
    user = session.get(UserRow, payload.get("sub"))
    if not user: raise HTTPException(401, "User not found")
    return user

class AuthRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)

class Activity(BaseModel):
    id: str
    source: str
    external_id: Optional[str] = None
    kind: str = "TRAINING"
    race_id: Optional[str] = None
    started_at: datetime
    duration_seconds: int
    distance_meters: float
    avg_heart_rate: Optional[float] = None
    elevation_gain_meters: Optional[float] = None
    avg_pace_seconds_per_km: Optional[float] = None
    updated_at: Optional[datetime] = None

class Goal(BaseModel):
    id: Optional[str] = None
    name: str
    target_value: float
    current_value: float = 0
    unit: str
    deadline: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class PlanRequest(BaseModel):
    weekly_km: float
    previous_weekly_km: float = 0
    load_score: int = 50
    next_race_days: Optional[int] = None
    baseline_pace_seconds_per_km: Optional[float] = None

@app.get("/health")
def health(): return {"status":"ok","service":"runwise-api","version":APP_VERSION,"database":engine.url.get_backend_name(),"environment":APP_ENV}

@app.get("/ready")
def ready(session: Session = Depends(db)):
    try:
        session.execute(sql_text("SELECT 1"))
        return {"status":"ready","database":"ok","version":APP_VERSION}
    except Exception:
        raise HTTPException(503, "Database unavailable")

@app.post("/v1/auth/register")
def register(req: AuthRequest, session: Session = Depends(db)):
    email=req.email.strip().lower()
    if session.scalar(select(UserRow).where(UserRow.email==email)): raise HTTPException(409,"Email already registered")
    user=UserRow(id=str(uuid4()),email=email,password_hash=password_hash(req.password)); session.add(user); session.commit()
    return {"access_token":token_for(user),"token_type":"bearer","user":{"id":user.id,"email":user.email}}

@app.post("/v1/auth/login")
def login(req: AuthRequest, session: Session = Depends(db)):
    user=session.scalar(select(UserRow).where(UserRow.email==req.email.strip().lower()))
    if not user or not password_verify(req.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    return {"access_token":token_for(user),"token_type":"bearer","user":{"id":user.id,"email":user.email}}

@app.get("/v1/me")
def me(user: UserRow = Depends(current_user)): return {"id":user.id,"email":user.email}

def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def has_remote_change(updated_at: datetime, base_since: Optional[datetime]) -> bool:
    """Optimistic concurrency with normalized UTC-aware timestamps."""
    remote = _utc(updated_at)
    base = _utc(base_since)
    return base is not None and remote is not None and remote > base

@app.post("/v1/sync/activities")
def sync_activities(items: list[Activity], base_since: Optional[datetime] = Query(default=None), user: UserRow = Depends(current_user), session: Session = Depends(db)):
    count=0
    conflicts=[]
    for a in items:
        row=session.get(ActivityRow,a.id)
        if row and row.user_id != user.id: continue
        if row and has_remote_change(row.updated_at, base_since):
            conflicts.append(a.id)
            continue
        if not row:
            row=ActivityRow(id=a.id,user_id=user.id,source=a.source,external_id=a.external_id,kind=a.kind,race_id=a.race_id,started_at=a.started_at,duration_seconds=a.duration_seconds,distance_meters=a.distance_meters,avg_heart_rate=a.avg_heart_rate,elevation_gain_meters=a.elevation_gain_meters,avg_pace_seconds_per_km=a.avg_pace_seconds_per_km); session.add(row)
        else:
            values = a.model_dump(exclude={"id", "updated_at"})
            if any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items(): setattr(row, k, v)
        count += 1
    session.commit(); return {"accepted":count,"conflicts":conflicts}

@app.get("/v1/sync/activities")
def pull_activities(since: Optional[datetime]=None, user: UserRow=Depends(current_user), session: Session=Depends(db)):
    q=select(ActivityRow).where(ActivityRow.user_id==user.id)
    if since: q=q.where(ActivityRow.updated_at>since)
    rows=session.scalars(q.order_by(ActivityRow.started_at.desc())).all()
    return {"items":[Activity(id=r.id,source=r.source,external_id=r.external_id,kind=r.kind,race_id=r.race_id,started_at=r.started_at,duration_seconds=r.duration_seconds,distance_meters=r.distance_meters,avg_heart_rate=r.avg_heart_rate,elevation_gain_meters=r.elevation_gain_meters,avg_pace_seconds_per_km=r.avg_pace_seconds_per_km,updated_at=r.updated_at).model_dump(mode="json") for r in rows]}

@app.post("/v1/goals")
def create_goal(goal: Goal, user: UserRow=Depends(current_user), session: Session=Depends(db)):
    row=GoalRow(id=goal.id or str(uuid4()),user_id=user.id,name=goal.name,target_value=goal.target_value,current_value=goal.current_value,unit=goal.unit,deadline=goal.deadline); session.add(row); session.commit(); return {"accepted":True,"goal":goal.model_copy(update={"id":row.id}).model_dump(mode="json")}

@app.post("/v1/sync/goals")
def sync_goals(items: list[Goal], base_since: Optional[datetime]=Query(default=None), user: UserRow=Depends(current_user), session: Session=Depends(db)):
    accepted=0
    conflicts=[]
    for g in items:
        row=session.get(GoalRow,g.id) if g.id else None
        if row and row.user_id != user.id: continue
        if row and has_remote_change(row.updated_at, base_since):
            conflicts.append(g.id)
            continue
        if not row:
            row=GoalRow(id=g.id or str(uuid4()),user_id=user.id,name=g.name,target_value=g.target_value,current_value=g.current_value,unit=g.unit,deadline=g.deadline); session.add(row)
        else:
            values = {"name": g.name, "target_value": g.target_value, "current_value": g.current_value, "unit": g.unit, "deadline": g.deadline}
            if any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items(): setattr(row, k, v)
        accepted += 1
    session.commit(); return {"accepted":accepted,"conflicts":conflicts}

@app.get("/v1/sync/goals")
def pull_goals(since: Optional[datetime]=None, user: UserRow=Depends(current_user), session: Session=Depends(db)):
    q=select(GoalRow).where(GoalRow.user_id==user.id)
    if since: q=q.where(GoalRow.updated_at>since)
    rows=session.scalars(q.order_by(GoalRow.deadline.asc())).all()
    return {"items":[Goal(id=r.id,name=r.name,target_value=r.target_value,current_value=r.current_value,unit=r.unit,deadline=r.deadline,updated_at=r.updated_at).model_dump(mode="json") for r in rows]}

class RaceSync(BaseModel):
    id: str
    provider: str = "LOCAL"
    external_id: Optional[str] = None
    name: str
    date: datetime
    distance_meters: Optional[float] = None
    location: Optional[str] = None
    registration_status: str = "UNKNOWN"
    updated_at: Optional[datetime] = None

@app.post("/v1/sync/races")
def sync_races(items: list[RaceSync], base_since: Optional[datetime]=Query(default=None), user: UserRow=Depends(current_user), session: Session=Depends(db)):
    accepted=0
    conflicts=[]
    for r in items:
        row=session.get(RaceRow, r.id)
        if row and row.user_id != user.id: continue
        if row and has_remote_change(row.updated_at, base_since):
            conflicts.append(r.id)
            continue
        if not row:
            row=RaceRow(id=r.id,user_id=user.id,provider=r.provider,external_id=r.external_id,name=r.name,date=r.date,distance_meters=r.distance_meters,location=r.location,registration_status=r.registration_status)
            session.add(row)
        else:
            values = {"provider": r.provider, "external_id": r.external_id, "name": r.name, "date": r.date, "distance_meters": r.distance_meters, "location": r.location, "registration_status": r.registration_status}
            if any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items(): setattr(row, k, v)
        accepted += 1
    session.commit()
    return {"accepted":accepted,"conflicts":conflicts}

@app.get("/v1/sync/races")
def pull_races(since: Optional[datetime]=None, user: UserRow=Depends(current_user), session: Session=Depends(db)):
    q=select(RaceRow).where(RaceRow.user_id==user.id)
    if since: q=q.where(RaceRow.updated_at>since)
    rows=session.scalars(q.order_by(RaceRow.date.asc())).all()
    return {"items":[RaceSync(id=r.id,provider=r.provider,external_id=r.external_id,name=r.name,date=r.date,distance_meters=r.distance_meters,location=r.location,registration_status=r.registration_status,updated_at=r.updated_at).model_dump(mode="json") for r in rows]}

class PlannedWorkout(BaseModel):
    id: str
    date: datetime
    type: str
    title: str
    description: str = ""
    target_distance_meters: Optional[float] = None
    target_duration_seconds: Optional[int] = None
    target_pace_min_seconds_per_km: Optional[float] = None
    target_pace_max_seconds_per_km: Optional[float] = None
    completed: bool = False
    skipped: bool = False
    generated_reason: Optional[str] = None
    updated_at: Optional[datetime] = None

@app.post("/v1/sync/planned-workouts")
def sync_planned_workouts(items: list[PlannedWorkout], base_since: Optional[datetime]=Query(default=None), user: UserRow=Depends(current_user), session: Session=Depends(db)):
    accepted=0
    conflicts=[]
    for w in items:
        row=session.get(PlannedWorkoutRow,w.id)
        if row and row.user_id != user.id: continue
        if row and has_remote_change(row.updated_at, base_since):
            conflicts.append(w.id)
            continue
        if not row:
            row=PlannedWorkoutRow(id=w.id,user_id=user.id,date=w.date,type=w.type,title=w.title,description=w.description,target_distance_meters=w.target_distance_meters,target_duration_seconds=w.target_duration_seconds,target_pace_min_seconds_per_km=w.target_pace_min_seconds_per_km,target_pace_max_seconds_per_km=w.target_pace_max_seconds_per_km,completed=w.completed,skipped=w.skipped,generated_reason=w.generated_reason)
            session.add(row)
        else:
            values = {"date": w.date, "type": w.type, "title": w.title, "description": w.description, "target_distance_meters": w.target_distance_meters, "target_duration_seconds": w.target_duration_seconds, "target_pace_min_seconds_per_km": w.target_pace_min_seconds_per_km, "target_pace_max_seconds_per_km": w.target_pace_max_seconds_per_km, "completed": w.completed, "skipped": w.skipped, "generated_reason": w.generated_reason}
            if any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items(): setattr(row, k, v)
        accepted += 1
    session.commit()
    return {"accepted":accepted,"conflicts":conflicts}

@app.get("/v1/sync/planned-workouts")
def pull_planned_workouts(since: Optional[datetime]=None, user: UserRow=Depends(current_user), session: Session=Depends(db)):
    q=select(PlannedWorkoutRow).where(PlannedWorkoutRow.user_id==user.id)
    if since: q=q.where(PlannedWorkoutRow.updated_at>since)
    rows=session.scalars(q.order_by(PlannedWorkoutRow.date.asc())).all()
    return {"items":[PlannedWorkout(id=r.id,date=r.date,type=r.type,title=r.title,description=r.description,target_distance_meters=r.target_distance_meters,target_duration_seconds=r.target_duration_seconds,target_pace_min_seconds_per_km=r.target_pace_min_seconds_per_km,target_pace_max_seconds_per_km=r.target_pace_max_seconds_per_km,completed=r.completed,skipped=r.skipped,generated_reason=r.generated_reason,updated_at=r.updated_at).model_dump(mode="json") for r in rows]}

@app.post("/v1/coach/plan")
def generate_plan(req: PlanRequest):
    if req.load_score >= 80: target=max(15,req.weekly_km*0.85); reason="carga elevada: redução de volume"
    elif req.weekly_km <= 0: target=20; reason="base inicial"
    else: target=min(req.weekly_km*1.08,req.weekly_km+8); reason="progressão gradual"
    if req.next_race_days is not None and req.next_race_days<=7: reason="semana de prova: taper"; target*=0.65
    easy=req.baseline_pace_seconds_per_km or 390; quality=easy*0.88
    return {"weekly_target_km":round(target,1),"reason":reason,"sessions":[{"day":"MON","type":"EASY","km":round(target*.18,1),"pace":[round(easy*1.05),round(easy*1.20)]},{"day":"TUE","type":"REST","km":0},{"day":"WED","type":"INTERVALS","km":round(target*.16,1),"pace":[round(quality*.95),round(quality*1.05)]},{"day":"THU","type":"REST","km":0},{"day":"FRI","type":"TEMPO","km":round(target*.18,1),"pace":[round(easy*.92),round(easy)]},{"day":"SAT","type":"RECOVERY","km":round(target*.10,1)},{"day":"SUN","type":"LONG_RUN","km":round(target*.35,1),"pace":[round(easy*1.05),round(easy*1.18)]}]}

@app.post("/v1/coach/adjust")
def adjust_plan(req: PlanRequest, completed_km: float=0, missed_sessions: int=0):
    plan=generate_plan(req)
    if missed_sessions>=2: plan["reason"]+="; sessões falhadas: não compensar tudo de uma vez"; plan["weekly_target_km"]=round(plan["weekly_target_km"]*.9,1)
    elif completed_km>req.weekly_km*1.2 and req.load_score>=70: plan["reason"]+="; excesso de volume: recuperação"; plan["weekly_target_km"]=round(plan["weekly_target_km"]*.85,1)
    return plan

class TchacoRace(BaseModel):
    external_id:str; name:str; date:datetime; distance_meters:Optional[float]=None; location:Optional[str]=None; registration_status:str="UNKNOWN"

@app.post("/v1/integrations/tchaco/races")
def ingest_tchaco_races(races:list[TchacoRace], user:UserRow=Depends(current_user), session:Session=Depends(db)):
    accepted=[]
    for r in races:
        row=session.scalar(select(RaceRow).where(RaceRow.user_id==user.id, RaceRow.provider=="TCHACO", RaceRow.external_id==r.external_id))
        if not row:
            row=RaceRow(id=str(uuid4()),user_id=user.id,provider="TCHACO",external_id=r.external_id,name=r.name,date=r.date,distance_meters=r.distance_meters,location=r.location,registration_status=r.registration_status)
            session.add(row)
        else:
            row.name=r.name; row.date=r.date; row.distance_meters=r.distance_meters; row.location=r.location; row.registration_status=r.registration_status
        accepted.append(r.external_id)
    session.commit()
    return {"accepted":len(accepted),"provider":"TCHACO","external_ids":accepted}

@app.post("/v1/integrations/tchaco/webhook")
async def tchaco_webhook(request:Request, session:Session=Depends(db)):
    if not TCHACO_WEBHOOK_SECRET:
        raise HTTPException(503,"TCHACO webhook integration is not configured")
    raw=await request.body()
    signature=request.headers.get("X-TCHACO-Signature","")
    expected=hmac.new(TCHACO_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(401,"Invalid TCHACO webhook signature")
    try:
        payload=json.loads(raw.decode("utf-8"))
        user_id=str(payload["user_id"])
        user=session.get(UserRow,user_id)
        if not user: raise ValueError("unknown user")
        race=TchacoRace.model_validate(payload["race"])
    except Exception:
        raise HTTPException(400,"Invalid TCHACO webhook payload")
    row=session.scalar(select(RaceRow).where(RaceRow.user_id==user.id, RaceRow.provider=="TCHACO", RaceRow.external_id==race.external_id))
    if not row:
        row=RaceRow(id=str(uuid4()),user_id=user.id,provider="TCHACO",external_id=race.external_id,name=race.name,date=race.date,distance_meters=race.distance_meters,location=race.location,registration_status=race.registration_status)
        session.add(row)
    else:
        row.name=race.name; row.date=race.date; row.distance_meters=race.distance_meters; row.location=race.location; row.registration_status=race.registration_status
    session.commit()
    return {"accepted":True,"race_id":row.id,"provider":"TCHACO"}

@app.get("/v1/motivation/today")
def daily_motivation():
    phrases=["Hoje não precisas de correr perfeito. Precisas de começar.","Consistência vence a inspiração quando a meta é de longo prazo.","Corre com controlo hoje para teres pernas amanhã.","Cada treino é uma conversa entre o atleta de hoje e o atleta que queres ser.","O ritmo certo é aquele que te permite repetir o esforço com qualidade.","Não compenses um treino perdido exagerando no seguinte. Volta ao plano.","A recuperação também faz parte do treino."]
    return {"date":date.today().isoformat(),"text":phrases[date.today().toordinal()%len(phrases)]}
