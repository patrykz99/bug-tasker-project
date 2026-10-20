import os
from contextlib import asynccontextmanager
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("DATABASE_URL must be configured with a PostgreSQL connection string")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=1, max_length=255)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=80)
    email: str | None = Field(default=None, min_length=1, max_length=255)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    completed: bool = False
    owner_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    completed: bool | None = None
    owner_id: int | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    completed: bool
    owner_id: int | None


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def ensure_owner_exists(db: Session, owner_id: int | None) -> None:
    if owner_id is not None and db.get(User, owner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Buggy Tasker API", version="0.1.0", lifespan=lifespan)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "message": "FastAPI is running!"}


@app.get("/healthz")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users", response_model=list[UserRead])
def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id).offset(offset).limit(limit)).all())


@app.get("/users/{user_id}", response_model=UserRead)
def read_user(user_id: int, db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    ensure_owner_exists(db, payload.owner_id)
    task = Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    owner_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> list[Task]:
    query = select(Task).order_by(Task.id)
    if owner_id is not None:
        query = query.where(Task.owner_id == owner_id)
    return list(db.scalars(query.offset(offset).limit(limit)).all())


@app.get("/tasks/{task_id}", response_model=TaskRead)
def read_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@app.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    changes = payload.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        ensure_owner_exists(db, changes["owner_id"])
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> Response:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)