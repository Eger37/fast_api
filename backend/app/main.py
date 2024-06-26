from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel, constr
from sqlalchemy.orm import Session
from . import models, database
from passlib.hash import bcrypt
import jwt
from jwt.exceptions import DecodeError
from cachetools import TTLCache

app = FastAPI()

SECRET_KEY = "secret_key"

# Define a constraint for the maximum payload size
MAX_PAYLOAD_SIZE_MB = 1
MAX_PAYLOAD_SIZE_BYTES = MAX_PAYLOAD_SIZE_MB * 1024 * 1024
TextWithMaxLength = constr(max_length=MAX_PAYLOAD_SIZE_BYTES)

# Cache for storing posts data
# Cache size is 1000, and TTL is 300 seconds (5 minutes)
posts_cache = TTLCache(maxsize=1000, ttl=300)


class UserCreate(BaseModel):
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


def create_user(db: Session, user: UserCreate):
    db_user = models.User(email=user.email, password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)


def create_access_token(data: dict, secret_key: str, expires_delta: int):
    to_encode = data.copy()
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm="HS256")
    return encoded_jwt


def get_email_from_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload.get("email")
        return email
    except DecodeError:
        return None


@app.post("/signup")
def create_user_endpoint(user: UserCreate, db: Session = Depends(database.get_db)):
    existing_user = get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    hashed_password = bcrypt.hash(user.password)
    db_user = models.User(email=user.email, password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    token = create_access_token(
        data={"email": user.email}, secret_key=SECRET_KEY, expires_delta=3600)  # Expires in 1 hour
    return {"token": token}


@app.post("/login")
def login(user: UserLogin, db: Session = Depends(database.get_db)):
    db_user = get_user_by_email(db, user.email)
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(
            status_code=401, detail="Incorrect email or password")
    token = create_access_token(
        data={"email": user.email}, secret_key=SECRET_KEY, expires_delta=3600)  # Expires in 1 hour
    return {"token": token}

# Post views


class Post(BaseModel):
    text: TextWithMaxLength


class PostDelete(BaseModel):
    post_id: int


class TokenAuth:
    def __init__(self, token: str = Depends(HTTPBearer())):
        self.token = token.credentials


def create_post(db: Session, text: str, author_id: int):
    db_post = models.Post(text=text, author_id=author_id)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post


def get_posts(db: Session):
    return db.query(models.Post).all()


def get_posts_by_user(db: Session, user_id: int):
    return db.query(models.Post).filter(models.Post.author_id == user_id).all()


def delete_post(db: Session, post_id: int, user_id: int):
    db_post = db.query(models.Post).filter(
        models.Post.id == post_id, models.Post.author_id == user_id).first()
    if not db_post:
        raise HTTPException(
            status_code=404, detail="Post not found or does not belong to the user")
    db.delete(db_post)
    db.commit()
    return db_post


@app.post("/add-post")
def create_post_endpoint(post: Post, token: str = Depends(TokenAuth), db: Session = Depends(database.get_db)):
    email = get_email_from_token(token.token)
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check payload size
    if len(post.text) > MAX_PAYLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400, detail="Payload size exceeds maximum limit")

    # Create post
    created_post = create_post(db, text=post.text, author_id=user.id)

    # Remove posts cache
    posts_cache.clear()

    return created_post


@app.get("/get-posts")
def get_posts_endpoint(token: str = Depends(TokenAuth), db: Session = Depends(database.get_db)):
    email = get_email_from_token(token.token)
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check if posts data is cached
    if user.email in posts_cache:
        return posts_cache[user.email]

    # Get posts from database
    user_posts = get_posts_by_user(db, user.id)

    # Cache posts data
    posts_cache[user.email] = user_posts

    return user_posts


@app.delete("/delete-post")
def delete_post_endpoint(post: PostDelete, token: str = Depends(TokenAuth), db: Session = Depends(database.get_db)):
    email = get_email_from_token(token.token)
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Delete post
    deleted_post = delete_post(db, post.post_id, user.id)

    # Remove posts cache
    posts_cache.clear()

    return deleted_post


@app.get("/db_init")
def db_init():
    database.Base.metadata.create_all(database.engine)
    return "good"


@app.get("/")
def read_root():
    return {"Hello": "World"}
